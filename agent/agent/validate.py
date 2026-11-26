"""The final status decision, with deterministic rules and no model.

The model can be confidently wrong. So "פתוחה" (ready for production) only happens when all the rules
below pass. Every reason is written in Hebrew into the "מה לבדוק" column for Rina.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .config import DUPLICATE_WINDOW_DAYS, STATUS_OK, STATUS_REVIEW
from .models import Candidate, Client, Decision, HistoryOrder, IntakeMessage
from .matching import strength

FINISH_RE = re.compile(r"^(RAL \d{4}|מגולוון|ללא צבע)$")


def _received_date(msg: IntakeMessage) -> date:
    try:
        return datetime.fromisoformat(msg.received_at).date()
    except ValueError:
        return date.today()


def decide(ex: dict, msg: IntakeMessage, clients: list[Client], candidates: list[Candidate],
           history: list[HistoryOrder]) -> Decision:
    reasons: list[str] = []
    notes: list[str] = list(ex.get("assumptions") or [])
    by_id = {c.id: c for c in clients}

    # --- client ---
    cid = ex["client"]["client_id"]
    det = candidates[0].client_id if candidates else None
    det_strength = strength(candidates)
    if msg.known_client_id:
        if cid and cid != msg.known_client_id:
            reasons.append("הסוכן זיהה לקוח אחר מזה של הקישור בפורטל")
        ex["client"]["client_id"] = cid = msg.known_client_id
    elif cid is None:
        reasons.append("לא זוהה לקוח")
    elif cid not in by_id:
        reasons.append(f"הסוכן החזיר מזהה לקוח שלא קיים ({cid})")
        ex["client"]["client_id"] = cid = None
    else:
        if det and det != cid:
            reasons.append(f"זיהוי הלקוח לא חד: הסוכן בחר '{by_id[cid].name}', ההתאמה לפי שם/טלפון מצביעה על '{by_id[det].name}'")
        elif det is None:
            reasons.append(f"הלקוח '{by_id[cid].name}' נבחר בלי ראיה מהשם או מהטלפון; לאשר")
        elif det_strength == "weak" or ex["client"]["confidence"] == "low":
            reasons.append(f"הלקוח '{by_id[cid].name}' זוהה רק לפי ראיה חלשה ({'; '.join(candidates[0].evidence)}); לאשר")

    # --- lines ---
    lines = ex.get("lines") or []
    if not lines:
        reasons.append("לא חולצו פריטים")
    for i, l in enumerate(lines, 1):
        tag = f"שורה {i} ({l['item_type']})"
        if not l.get("quantity") or l["quantity"] <= 0:
            reasons.append(f"{tag}: חסרה כמות")
        if l.get("width_cm") is None or l.get("height_cm") is None:
            reasons.append(f"{tag}: חסרות מידות")
        elif not (10 <= l["width_cm"] <= 2000 and 10 <= l["height_cm"] <= 1000):
            reasons.append(f"{tag}: מידות חריגות ({l['width_cm']:g}x{l['height_cm']:g}); לוודא יחידות")
        fin = l.get("finish")
        if not fin:
            reasons.append(f"{tag}: חסר גוון/גימור")
        elif not FINISH_RE.match(fin):
            reasons.append(f"{tag}: גימור לא מזוהה '{fin}'")
        if l["item_type"] == "אחר":
            reasons.append(f"{tag}: סוג פריט לא מזוהה")
        if l.get("derived_from_history"):
            reasons.append(f"{tag}: נבנתה מהזמנה קודמת; לאשר מול הלקוח")
        if l.get("confidence") == "low":
            reasons.append(f"{tag}: הסוכן לא בטוח בשורה")
        for issue in l.get("issues") or []:
            reasons.append(f"{tag}: {issue}")

    # --- date ---
    rd = ex.get("requested_date")
    recv = _received_date(msg)
    if not rd:
        reasons.append("לא צוין תאריך אספקה")
    else:
        try:
            d = date.fromisoformat(rd)
            if d < recv:
                reasons.append(f"תאריך האספקה {rd} כבר עבר")
            elif (d - recv).days < 3:
                notes.append(f"תאריך אספקה קרוב מאוד: {rd}")
        except ValueError:
            reasons.append(f"תאריך לא תקין: {rd}")
        if ex.get("date_interpretation"):
            notes.append(f"תאריך: '{ex.get('requested_date_text')}' ← {rd} ({ex['date_interpretation']})")

    # --- model flags ---
    for m in ex.get("missing_or_unclear") or []:
        reasons.append(m)

    # --- duplicates against the client's history ---
    if cid and lines:
        cutoff = recv - timedelta(days=DUPLICATE_WINDOW_DAYS)
        for o in history:
            try:
                od = date.fromisoformat(o.date) if o.date else None
            except ValueError:
                od = None
            for l in lines:
                for h in o.lines:
                    same = (h.item == l["item_type"] and h.width == l.get("width_cm")
                            and h.height == l.get("height_cm") and h.qty == l.get("quantity"))
                    if not same:
                        continue
                    if o.status == "בוטלה":
                        notes.append(f"פריט זהה ({l['item_type']} {h.width:g}x{h.height:g} x{h.qty:g}) היה בהזמנה {o.number} שבוטלה. ייתכן שזו הזמנה חוזרת")
                    elif od and od >= cutoff and not l.get("derived_from_history"):
                        reasons.append(f"חשד לכפילות: פריט זהה בהזמנה {o.number} מ-{o.date}")

    # dedupe, keep order
    reasons = list(dict.fromkeys(reasons))
    notes = list(dict.fromkeys(notes))
    return Decision(STATUS_REVIEW if reasons else STATUS_OK, reasons, notes)
