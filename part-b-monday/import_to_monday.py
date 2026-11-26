#!/usr/bin/env python3
"""
ייבוא הזמנות "מתכת הגליל" מקובץ האקסל ל-monday.com דרך ה-GraphQL API.

שני מצבים:
  python import_to_monday.py orders.xlsx
      ריצה יבשה: מנקה, מאחד ומפיק דוח (import_report.md + cleaned.json). לא נוגע ב-monday.

  MONDAY_TOKEN=xxx python import_to_monday.py orders.xlsx --apply [--workspace-id 123]
      יוצר את הלוחות (אם אינם קיימים) ומייבא. ריצה חוזרת לא יוצרת כפילויות.

מה הסקריפט עושה:
  1. קורא את גיליון ההזמנות לפי שמות הכותרות (לא לפי מיקום עמודה).
  2. מנרמל תאריכים, כמויות, מידות, גוונים, טלפונים וסטטוסים.
  3. מאחד לקוחות שמופיעים בכמה שמות (שם מנורמל, הכלה של שמות, או טלפון משותף).
  4. מסמן חשד לכפילות, שדות חסרים והנחות שהסקריפט עשה.
  5. מדלג על שורות שאינן הזמנות (ליד בלי לקוח ובלי פריט) ומדווח עליהן.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------------------
# מילונים
# ---------------------------------------------------------------------------

HEADER_ALIASES = {
    "num": ["מס", "מס'", "מספר", "מס הזמנה"],
    "date": ["תאריך"],
    "client": ["לקוח"],
    "contact": ["איש קשר"],
    "phone": ["טלפון"],
    "item": ["פריט"],
    "dims": ["מידות"],
    "qty": ["כמות"],
    "color": ["צבע", "גוון"],
    "status": ["סטטוס"],
    "notes": ["הערות"],
}

HEBREW_NUMBERS = {
    "אחד": 1, "אחת": 1, "שניים": 2, "שתיים": 2, "שני": 2, "שתי": 2,
    "שלושה": 3, "שלוש": 3, "ארבעה": 4, "ארבע": 4, "חמישה": 5, "חמש": 5,
    "שישה": 6, "שש": 6, "שבעה": 7, "שבע": 7, "שמונה": 8, "תשעה": 9, "תשע": 9,
    "עשרה": 10, "עשר": 10,
}

# שמות צבע שהופיעו בנתונים -> קוד RAL. כל המרה מסומנת בדוח כהנחה.
COLOR_NAMES = {
    "שחור": "RAL 9005",
    "אפור אנתרציט": "RAL 7016",
    "אנתרציט": "RAL 7016",
}
NO_COLOR = {"ללא", "ללא צבע", "-"}

# סטטוס באקסל -> (סטטוס הזמנה, שלב ייצור של השורה)
STATUS_MAP = {
    "ממתין":       ("פתוחה", "ממתין"),
    "חיתוך":       ("פתוחה", "חיתוך"),
    "כיפוף":       ("פתוחה", "כיפוף"),
    "ריתוך":       ("פתוחה", "ריתוך"),
    "בייצור":      ("פתוחה", "בייצור"),   # שלב לא ידוע: לא ממציאים
    "בצבע":        ("פתוחה", "בצבע"),
    "אריזה":       ("פתוחה", "אריזה"),
    "מוכן":        ("פתוחה", "מוכן"),
    "נשלח":        ("סופקה", "נשלח"),
    "בוטל":        ("בוטלה", None),
    "להצעת מחיר":  ("הצעת מחיר", None),
}

ORDER_STATUSES = ["טיוטה", "פתוחה", "סופקה חלקית", "סופקה", "בוטלה", "הצעת מחיר"]
LINE_STAGES = ["ממתין", "חיתוך", "כיפוף", "ריתוך", "בייצור", "בצבע", "אריזה", "מוכן", "נשלח"]
BILLING = ["לחיוב", "חויב"]
CHANNELS = ["מייל", "וואטסאפ", "טלפון", "הזמנת רכש", "אתר", "לא ידוע"]

GENERIC_NAME_WORDS = {"קבוצת", "קבוצה", "חברת", "חברה", "בעמ"}

# ---------------------------------------------------------------------------
# מודל
# ---------------------------------------------------------------------------


@dataclass
class Line:
    item_type: str
    width: float | None
    height: float | None
    dims_raw: str | None
    qty: int | None
    delivered: int | None
    color: str | None
    stage: str | None


@dataclass
class Order:
    source_row: int
    num: str
    date: str | None
    client_raw: str
    contact: str | None
    phone: str | None          # 050-1234567
    phone_e164: str | None     # +972501234567
    order_status: str
    billing: str | None
    urgent: bool
    project: str | None
    notes: str | None
    line: Line
    fixes: list = field(default_factory=list)    # תוקן אוטומטית
    review: list = field(default_factory=list)   # דורש בדיקה אנושית
    client_key: str | None = None


@dataclass
class Client:
    key: str
    name: str
    aliases: list
    contacts: list   # [{"name":..., "phone":..., "phone_e164":...}]
    primary_contact: str | None
    primary_phone: str | None
    primary_phone_e164: str | None


@dataclass
class Skipped:
    source_row: int
    num: str
    reason: str
    raw: dict


# ---------------------------------------------------------------------------
# נרמול שדות
# ---------------------------------------------------------------------------


def s(v) -> str:
    return "" if v is None else str(v).strip()


def parse_date(raw, default_year: int | None):
    """מחזיר (YYYY-MM-DD | None, הערות). מניח פורמט ישראלי יום/חודש."""
    notes = []
    if isinstance(raw, (dt.datetime, dt.date)):
        d = raw.date() if isinstance(raw, dt.datetime) else raw
        return d.isoformat(), notes
    t = s(raw)
    if not t:
        return None, ["תאריך חסר"]
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", t)
        if m:
            d, mo, y = map(int, m.groups())
            if y < 100:
                y += 2000
        else:
            m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})", t)
            if not m or default_year is None:
                return None, [f"תאריך לא מזוהה: '{t}'"]
            d, mo = map(int, m.groups())
            y = default_year
            notes.append(f"לתאריך '{t}' אין שנה; הושלמה {y} לפי שאר השורות")
    try:
        iso = dt.date(y, mo, d).isoformat()
    except ValueError:
        return None, [f"תאריך לא תקין: '{t}'"]
    if t != iso and not notes:
        notes.append(f"תאריך '{t}' ← {iso}")
    return iso, notes


def parse_qty(raw):
    t = s(raw)
    if not t:
        return None, None
    m = re.search(r"\d+", t)
    if m:
        q = int(m.group())
        return q, (None if t == m.group() else f"כמות '{t}' ← {q}")
    for word, n in HEBREW_NUMBERS.items():
        if word in t:
            return n, f"כמות במילים '{t}' ← {n}"
    return None, f"כמות לא מזוהה: '{t}'"


def parse_dims(raw):
    """רוחב x גובה בס"מ. מחזיר (w, h, הערה, דורש_בדיקה)."""
    t = s(raw)
    if not t:
        return None, None, "מידות חסרות", True
    norm = re.sub(r"[X×*]", "x", t)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*", norm)
    if m:
        w, h = float(m.group(1)), float(m.group(2))
        return w, h, (None if norm == t else f"מידות '{t}' ← {norm}"), False
    return None, None, f"מידות לא מספריות ('{t}'); נשמר הטקסט המקורי", True


def parse_color(raw):
    """מחזיר (גוון, הערה, דורש_בדיקה)."""
    t = s(raw)
    if not t:
        return None, "גוון חסר", True
    m = re.search(r"RAL\s*(\d{4})", t, re.I)
    if m:
        return f"RAL {m.group(1)}", None, False
    if t in NO_COLOR:
        return "ללא צבע", None, False
    if t in COLOR_NAMES:
        return COLOR_NAMES[t], f"שם צבע '{t}' ← {COLOR_NAMES[t]} (הנחה, לאשר מול הלקוח)", True
    return t, f"גוון לא מוכר: '{t}'", True


def parse_phone(raw):
    """מחזיר (תצוגה, E.164, הערה)."""
    t = s(raw)
    if not t:
        return None, None, None
    digits = re.sub(r"\D", "", t)
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    if re.fullmatch(r"05\d{8}", digits):
        disp = f"{digits[:3]}-{digits[3:]}"
    elif re.fullmatch(r"0[2-9]\d{7}", digits):
        disp = f"{digits[:2]}-{digits[2:]}"
    elif re.fullmatch(r"07\d{8}", digits):
        disp = f"{digits[:3]}-{digits[3:]}"
    else:
        return None, None, f"טלפון לא תקין: '{t}'"
    e164 = "+972" + digits[1:]
    return disp, e164, (None if disp == t else f"טלפון '{t}' ← {disp}")


def name_tokens(name: str) -> frozenset:
    n = re.sub(r"[\"'״׳.\-–,()]", "", name)
    n = n.replace("יי", "י").replace("וו", "ו")
    toks = {w for w in n.split() if w and w not in GENERIC_NAME_WORDS}
    return frozenset(toks)


def parse_notes(notes: str):
    """מחלץ מידע מובנה מהערות חופשיות."""
    out = {"urgent": False, "delivered": None, "project": None,
           "dup_of": None, "billing_check": False}
    if not notes:
        return out
    if "דחוף" in notes:
        out["urgent"] = True
    m = re.search(r"סופקו\s*(\d+)", notes)
    if m:
        out["delivered"] = int(m.group(1))
    m = re.search(r"פרויקט\s+(\S.*)", notes)
    if m:
        out["project"] = m.group(1).strip()
    m = re.search(r"כפול(?:ה)?\s+של\s+(\d+)", notes)
    if m:
        out["dup_of"] = m.group(1)
    if "חשבונית" in notes:
        out["billing_check"] = True
    return out


# ---------------------------------------------------------------------------
# קריאה וניקוי
# ---------------------------------------------------------------------------


def read_rows(path: str):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = [s(h) for h in rows[0]]
    idx = {}
    for key, names in HEADER_ALIASES.items():
        for i, h in enumerate(header):
            if h in names:
                idx[key] = i
                break
    missing = [k for k in ("num", "client", "item") if k not in idx]
    if missing:
        sys.exit(f"לא נמצאו כותרות חובה בגיליון: {missing}")
    out = []
    for r_i, r in enumerate(rows[1:], start=2):
        if not any(c not in (None, "") for c in r):
            continue
        out.append((r_i, {k: (r[i] if i < len(r) else None) for k, i in idx.items()}))
    return out


def guess_year(rows) -> int | None:
    years = []
    for _, r in rows:
        iso, _ = parse_date(r.get("date"), None)
        if iso:
            years.append(int(iso[:4]))
    return Counter(years).most_common(1)[0][0] if years else None


def clean(rows):
    year = guess_year(rows)
    orders, skipped = [], []
    for r_i, r in rows:
        num = s(r.get("num"))
        client_raw = s(r.get("client"))
        item = s(r.get("item"))
        status_raw = s(r.get("status"))
        notes = s(r.get("notes")) or None

        # ליד / פנייה בלי לקוח מזוהה ובלי פריט מוגדר = לא הזמנה
        no_client = (not client_raw) or "לברר" in client_raw
        no_spec = not s(r.get("dims")) and not s(r.get("qty"))
        if no_client and (no_spec or status_raw == "להצעת מחיר"):
            skipped.append(Skipped(r_i, num,
                "פנייה/ליד בלי לקוח ובלי פריט מוגדר. לא נפתחה הזמנה ולא נפתח לקוח; "
                "להעביר לרינה להצעת מחיר", {k: s(v) for k, v in r.items()}))
            continue

        fixes, review = [], []

        date, dnotes = parse_date(r.get("date"), year)
        for n in dnotes:
            (review if ("חסר" in n or "לא" in n or "אין שנה" in n) else fixes).append(n)

        qty, qn = parse_qty(r.get("qty"))
        if qn:
            (review if "לא מזוהה" in qn else fixes).append(qn)
        if qty is None and not qn:
            review.append("כמות חסרה")

        w, h, dn, d_review = parse_dims(r.get("dims"))
        if dn:
            (review if d_review else fixes).append(dn)

        color, cn, c_review = parse_color(r.get("color"))
        if cn:
            (review if c_review else fixes).append(cn)

        phone, e164, pn = parse_phone(r.get("phone"))
        if pn:
            (review if "לא תקין" in pn else fixes).append(pn)

        contact = s(r.get("contact")) or None
        if not contact:
            review.append("איש קשר חסר")
        if not phone:
            review.append("טלפון חסר")

        if status_raw in STATUS_MAP:
            order_status, stage = STATUS_MAP[status_raw]
            if stage == "בייצור":
                review.append("סטטוס 'בייצור' בלי שלב מדויק; לעדכן שלב")
        else:
            order_status, stage = "פתוחה", None
            review.append(f"סטטוס לא מוכר: '{status_raw}'")

        nt = parse_notes(notes or "")
        delivered = nt["delivered"]
        billing = None
        if order_status == "סופקה":
            delivered = delivered if delivered is not None else qty
            billing = "לחיוב"
            if nt["billing_check"]:
                review.append("סופקה ולא ברור אם חויבה ('חשבונית?'); סומן 'לחיוב'")
        if delivered is not None and qty and 0 < delivered < qty:
            order_status = "סופקה חלקית"
            billing = "לחיוב"
            fixes.append(f"אספקה חלקית מההערות: {delivered} מתוך {qty} ← סטטוס 'סופקה חלקית'")
        if nt["urgent"]:
            fixes.append("'דחוף' מההערות ← עמודת דחוף")
        if nt["project"]:
            fixes.append(f"פרויקט מההערות ← '{nt['project']}'")
        if nt["dup_of"]:
            review.append(f"בהערות: חשד לכפילות של {nt['dup_of']}")
        if "תברר" in (notes or ""):
            review.append("פרטים חסרים לפי ההערות ('תברר')")

        orders.append(Order(
            source_row=r_i, num=num, date=date, client_raw=client_raw,
            contact=contact, phone=phone, phone_e164=e164,
            order_status=order_status, billing=billing, urgent=nt["urgent"],
            project=nt["project"], notes=notes,
            line=Line(item_type=item or "לא ידוע", width=w, height=h,
                      dims_raw=s(r.get("dims")) or None, qty=qty,
                      delivered=delivered, color=color, stage=stage),
            fixes=fixes, review=review))

    clients = resolve_clients(orders)
    flag_duplicates(orders)
    check_date_order(orders)
    return orders, clients, skipped


def resolve_clients(orders):
    """איחוד לקוחות: אותו שם מנורמל, שם שמוכל בשם אחר, או אותו טלפון."""
    parent = list(range(len(orders)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        parent[find(a)] = find(b)

    toks = [name_tokens(o.client_raw) for o in orders]
    for i in range(len(orders)):
        for j in range(i + 1, len(orders)):
            a, b = toks[i], toks[j]
            same_name = a and b and (a == b or a <= b or b <= a)
            same_phone = orders[i].phone and orders[i].phone == orders[j].phone
            if same_name or same_phone:
                union(i, j)

    groups = defaultdict(list)
    for i in range(len(orders)):
        groups[find(i)].append(i)

    clients = {}
    for members in groups.values():
        names = [orders[i].client_raw for i in members]
        canonical = max(names, key=lambda n: (len(n), names.count(n)))
        key = f"c{len(clients) + 1}"
        # אנשי קשר: איחוד לפי טלפון, או שם שהוא תחילית של שם מלא יותר
        contacts = []
        for i in members:
            o = orders[i]
            if not o.contact and not o.phone:
                continue
            match = None
            for c in contacts:
                if o.phone and c["phone"] == o.phone:
                    match = c
                elif o.contact and c["name"] and (
                        c["name"].startswith(o.contact) or o.contact.startswith(c["name"])):
                    if not (o.phone and c["phone"] and o.phone != c["phone"]):
                        match = c
                if match:
                    break
            if match:
                if o.contact and len(o.contact) > len(match["name"] or ""):
                    match["name"] = o.contact
                if o.phone and not match["phone"]:
                    match["phone"], match["phone_e164"] = o.phone, o.phone_e164
            else:
                contacts.append({"name": o.contact, "phone": o.phone,
                                 "phone_e164": o.phone_e164})
        primary = contacts[0] if contacts else {"name": None, "phone": None, "phone_e164": None}
        clients[key] = Client(
            key=key, name=canonical,
            aliases=sorted(set(names) - {canonical}),
            contacts=contacts, primary_contact=primary["name"],
            primary_phone=primary["phone"], primary_phone_e164=primary["phone_e164"])
        for i in members:
            orders[i].client_key = key
            if orders[i].client_raw != canonical:
                orders[i].fixes.append(f"לקוח '{orders[i].client_raw}' אוחד ל-'{canonical}'")
            # השלמת איש קשר/טלפון מהכרטיס המאוחד
            for c in contacts:
                if orders[i].contact and c["name"] and c["name"].startswith(orders[i].contact):
                    if c["name"] != orders[i].contact:
                        orders[i].fixes.append(f"איש קשר '{orders[i].contact}' ← '{c['name']}'")
                        orders[i].contact = c["name"]
                    if not orders[i].phone and c["phone"]:
                        orders[i].phone, orders[i].phone_e164 = c["phone"], c["phone_e164"]
                        orders[i].fixes.append(f"טלפון הושלם מכרטיס הלקוח: {c['phone']}")
                        if "טלפון חסר" in orders[i].review:
                            orders[i].review.remove("טלפון חסר")
                    break
    return clients


def flag_duplicates(orders):
    """אותו לקוח, פריט, מידות וכמות בהפרש של עד 14 יום = חשד לכפילות. לא מוחקים."""
    for i, a in enumerate(orders):
        for b in orders[i + 1:]:
            if (a.client_key == b.client_key and a.line.item_type == b.line.item_type
                    and a.line.width == b.line.width and a.line.height == b.line.height
                    and a.line.qty == b.line.qty and a.date and b.date
                    and abs((dt.date.fromisoformat(b.date) - dt.date.fromisoformat(a.date)).days) <= 14):
                msg = f"חשד לכפילות של {a.num} (אותו לקוח, פריט, מידות וכמות)"
                if not any(a.num in x and "כפילות" in x for x in b.review):
                    b.review.append(msg)


def check_date_order(orders):
    """מספרי ההזמנה רציפים, אז התאריכים אמורים לעלות. סטייה מרמזת על פענוח יום/חודש שגוי."""
    prev = None
    for o in sorted(orders, key=lambda o: int(o.num) if o.num.isdigit() else 0):
        if o.date and prev and o.date < prev.date:
            o.review.append(f"התאריך {o.date} מוקדם מזה של {prev.num}; לבדוק יום/חודש")
        if o.date:
            prev = o


# ---------------------------------------------------------------------------
# דוח
# ---------------------------------------------------------------------------


def write_report(path, orders, clients, skipped, source):
    L = []
    L.append("# דוח ייבוא: הזמנות מתכת הגליל ל-monday\n")
    L.append(f"מקור: `{os.path.basename(source)}` · הופק: {dt.datetime.now():%Y-%m-%d %H:%M}\n")
    n_review = sum(1 for o in orders if o.review)
    L.append("## סיכום\n")
    L.append(f"- שורות בקובץ: {len(orders) + len(skipped)}")
    L.append(f"- הזמנות שיובאו: {len(orders)} (מתוכן {n_review} מסומנות לבדיקה)")
    L.append(f"- לקוחות אחרי איחוד: {len(clients)} (מ-{len({o.client_raw for o in orders})} שמות שונים)")
    L.append(f"- שורות שלא יובאו: {len(skipped)}\n")

    L.append("## לקוחות שאוחדו\n")
    L.append("| לקוח (שם קבוע) | שמות נוספים שאוחדו | אנשי קשר |")
    L.append("| --- | --- | --- |")
    for c in clients.values():
        contacts = "; ".join(f"{x['name'] or '?'} {x['phone'] or ''}".strip() for x in c.contacts) or "—"
        L.append(f"| {c.name} | {', '.join(c.aliases) or '—'} | {contacts} |")
    L.append("")

    L.append("## לא יובא\n")
    if skipped:
        for sk in skipped:
            raw = ", ".join(f"{k}={v}" for k, v in sk.raw.items() if v)
            L.append(f"- **{sk.num}** (שורה {sk.source_row}): {sk.reason}. נתוני המקור: {raw}")
    else:
        L.append("- אין")
    L.append("")

    L.append("## דורש בדיקה אנושית\n")
    L.append("| מס' | לקוח | מה לבדוק |")
    L.append("| --- | --- | --- |")
    for o in orders:
        if o.review:
            L.append(f"| {o.num} | {clients[o.client_key].name} | {'; '.join(o.review)} |")
    L.append("")

    L.append("## תוקן אוטומטית\n")
    L.append("| מס' | תיקונים |")
    L.append("| --- | --- |")
    for o in orders:
        if o.fixes:
            L.append(f"| {o.num} | {'; '.join(o.fixes)} |")
    L.append("")

    L.append("## הנחות כלליות\n")
    L.append("- תאריכים בפורמט ישראלי (יום/חודש). הסקריפט מוודא שהתאריכים עולים יחד עם מספרי ההזמנה.")
    L.append("- מידות הן רוחב x גובה בס\"מ.")
    L.append("- לכל שורה באקסל יש הזמנה אחת עם פריט אחד. בהזמנות חדשות יהיו כמה פריטים (שורות משנה).")
    L.append("- חשד לכפילות לא נמחק: מיובא ומסומן, וההחלטה אצל רינה.")
    L.append("- מספר ההזמנה המקורי נשמר בעמודה \"מס' במקור\", ולכן ריצה חוזרת לא יוצרת כפילות.")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# ---------------------------------------------------------------------------
# monday API
# ---------------------------------------------------------------------------

API_URL = "https://api.monday.com/v2"

BOARD_CLIENTS = "לקוחות"
BOARD_ORDERS = "הזמנות"

CLIENT_COLUMNS = [
    ("איש קשר ראשי", "text", None),
    ("טלפון", "phone", None),
    ("אנשי קשר", "long_text", None),
    ("שמות נוספים", "long_text", None),
    ("מס' לקוח בחשבשבת", "text", None),
]


def order_columns(clients_board_id):
    return [
        ("לקוח", "board_relation", {"boardIds": [int(clients_board_id)],
                                    "allowCreateReflectionColumn": True}),
        ("איש קשר", "text", None),
        ("טלפון", "phone", None),
        ("תאריך קבלה", "date", None),
        ("תאריך אספקה", "date", None),
        ("סטטוס הזמנה", "status", ORDER_STATUSES),
        ("חיוב", "status", BILLING),
        ("דחוף", "checkbox", None),
        ("פרויקט / אתר", "text", None),
        ("ערוץ", "status", CHANNELS),
        ("מס' במקור", "text", None),
        ("הערות", "long_text", None),
        ("מה לבדוק", "long_text", None),
    ]


LINE_COLUMNS = [
    ("סוג פריט", "dropdown", None),
    ("רוחב (ס\"מ)", "numbers", None),
    ("גובה (ס\"מ)", "numbers", None),
    ("מידות במקור", "text", None),
    ("כמות", "numbers", None),
    ("סופק", "numbers", None),
    ("גוון", "dropdown", None),
    ("שלב", "status", LINE_STAGES),
    ("נשלח לצבע", "date", None),
    ("חזר מצבע", "date", None),
]


class Monday:
    def __init__(self, token, api_version=None):
        import requests  # רק במצב --apply
        self.requests = requests
        self.headers = {"Content-Type": "application/json"}
        if token:  # בסביבה שכבר מאומתת מול monday אין צורך בטוקן
            self.headers["Authorization"] = token
        if api_version:
            self.headers["API-Version"] = api_version

    def q(self, query, variables=None, retries=5):
        for attempt in range(retries):
            r = self.requests.post(API_URL, headers=self.headers,
                                   json={"query": query, "variables": variables or {}},
                                   timeout=60)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", 10)))
                continue
            data = r.json()
            errs = data.get("errors") or ([{"message": data["error_message"]}]
                                          if "error_message" in data else None)
            if errs:
                msg = json.dumps(errs, ensure_ascii=False)
                if "Complexity" in msg or "rate" in msg.lower():
                    time.sleep(10 * (attempt + 1))
                    continue
                raise RuntimeError(msg)
            return data["data"]
        raise RuntimeError("monday API: נכשל אחרי כמה ניסיונות")

    # --- לוחות ועמודות ---
    def find_board(self, name, workspace_id):
        data = self.q("query ($ws:[ID]) { boards(limit:500, workspace_ids:$ws) { id name } }",
                      {"ws": [workspace_id] if workspace_id else None})
        for b in data["boards"]:
            if b["name"] == name:
                return b["id"]
        return None

    def create_board(self, name, workspace_id):
        data = self.q("mutation ($n:String!, $ws:ID) "
                      "{ create_board(board_name:$n, board_kind:public, workspace_id:$ws) { id } }",
                      {"n": name, "ws": workspace_id})
        return data["create_board"]["id"]

    def columns(self, board_id):
        data = self.q("query ($b:[ID!]) { boards(ids:$b) { columns { id title type } } }",
                      {"b": [board_id]})
        return {c["title"]: c["id"] for c in data["boards"][0]["columns"]}

    def ensure_columns(self, board_id, specs):
        existing = self.columns(board_id)
        ids = {}
        for title, ctype, extra in specs:
            if title in existing:
                ids[title] = existing[title]
                continue
            defaults = None
            if ctype == "status" and extra:
                # מפתח 5 שמור לערך הריק בעמודות סטטוס
                keys = [k for k in range(len(extra) + 1) if k != 5][:len(extra)]
                defaults = {"labels": {str(k): lab for k, lab in zip(keys, extra)}}
            elif ctype == "board_relation":
                defaults = extra
            mutation = ("mutation ($b:ID!, $t:String!, $c:ColumnType!, $d:JSON) "
                        "{ create_column(board_id:$b, title:$t, column_type:$c, defaults:$d) { id } }")
            # נבדק מול monday (נובמבר 2026): עמודת חיבור מקבלת defaults כאובייקט,
            # ועמודת סטטוס מקבלת אותו רק כמחרוזת JSON. הסדר נשמר ככה, עם fallback לשני הכיוונים.
            # בעמודת סטטוס, אם הכל נדחה, יוצרים בלי תוויות והן נוצרות בזמן הייבוא.
            if defaults is None:
                attempts = [None]
            elif ctype == "status":
                attempts = [json.dumps(defaults, ensure_ascii=False), defaults]
            else:
                attempts = [defaults, json.dumps(defaults, ensure_ascii=False)]
            if defaults is not None and ctype != "board_relation":
                attempts.append(None)
            last_err = None
            for d in attempts:
                try:
                    data = self.q(mutation, {"b": board_id, "t": title, "c": ctype, "d": d})
                    break
                except RuntimeError as e:
                    last_err = e
            else:
                raise last_err
            ids[title] = data["create_column"]["id"]
            print(f"  + עמודה: {title} ({ctype})")
        return ids

    # --- פריטים ---
    def find_item(self, board_id, column_id, value):
        data = self.q("query ($b:ID!, $c:String!, $v:[String]!) { items_page_by_column_values("
                      "board_id:$b, limit:1, columns:[{column_id:$c, column_values:$v}]) { items { id } } }",
                      {"b": board_id, "c": column_id, "v": [value]})
        items = data["items_page_by_column_values"]["items"]
        return items[0]["id"] if items else None

    def create_item(self, board_id, name, values):
        data = self.q("mutation ($b:ID!, $n:String!, $v:JSON) { create_item(board_id:$b, "
                      "item_name:$n, column_values:$v, create_labels_if_missing:true) { id } }",
                      {"b": board_id, "n": name, "v": json.dumps(values, ensure_ascii=False)})
        return data["create_item"]["id"]

    def create_subitem(self, parent_id, name, values):
        data = self.q("mutation ($p:ID!, $n:String!, $v:JSON) { create_subitem(parent_item_id:$p, "
                      "item_name:$n, column_values:$v, create_labels_if_missing:true) "
                      "{ id board { id } } }",
                      {"p": parent_id, "n": name, "v": json.dumps(values, ensure_ascii=False)})
        return data["create_subitem"]["id"], data["create_subitem"]["board"]["id"]

    def delete_item(self, item_id):
        self.q("mutation ($i:ID!) { delete_item(item_id:$i) { id } }", {"i": item_id})


def phone_val(e164):
    return {"phone": e164, "countryShortName": "IL"} if e164 else None


def compact(d):
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def apply_to_monday(orders, clients, token, workspace_id, api_version, state_path):
    m = Monday(token, api_version)
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}

    # 1. לוחות
    clients_board = state.get("clients_board") or m.find_board(BOARD_CLIENTS, workspace_id) \
        or m.create_board(BOARD_CLIENTS, workspace_id)
    orders_board = state.get("orders_board") or m.find_board(BOARD_ORDERS, workspace_id) \
        or m.create_board(BOARD_ORDERS, workspace_id)
    ccol = m.ensure_columns(clients_board, CLIENT_COLUMNS)
    ocol = m.ensure_columns(orders_board, order_columns(clients_board))

    # 2. לוח שורות ההזמנה (subitems) נוצר רק עם שורת המשנה הראשונה
    lines_board = state.get("lines_board")
    if not lines_board:
        tmp = m.create_item(orders_board, "__setup__", {})
        sub, lines_board = m.create_subitem(tmp, "__setup__", {})
        m.delete_item(tmp)
    lcol = m.ensure_columns(lines_board, LINE_COLUMNS)

    state.update(clients_board=clients_board, orders_board=orders_board, lines_board=lines_board)
    json.dump(state, open(state_path, "w"), indent=2)

    # 3. לקוחות
    client_ids = {}
    for c in clients.values():
        cid = m.find_item(clients_board, "name", c.name)
        if not cid:
            cid = m.create_item(clients_board, c.name, compact({
                ccol["איש קשר ראשי"]: c.primary_contact,
                ccol["טלפון"]: phone_val(c.primary_phone_e164),
                ccol["אנשי קשר"]: {"text": "\n".join(
                    f"{x['name'] or '?'} {x['phone'] or ''}".strip() for x in c.contacts)}
                    if c.contacts else None,
                ccol["שמות נוספים"]: {"text": "\n".join(c.aliases)} if c.aliases else None,
            }))
            print(f"  + לקוח: {c.name}")
        client_ids[c.key] = int(cid)

    # 4. הזמנות + שורות
    created = skipped_existing = 0
    for o in orders:
        if m.find_item(orders_board, ocol["מס' במקור"], o.num):
            skipped_existing += 1
            continue
        cname = clients[o.client_key].name
        values = compact({
            ocol["לקוח"]: {"item_ids": [client_ids[o.client_key]]},
            ocol["איש קשר"]: o.contact,
            ocol["טלפון"]: phone_val(o.phone_e164),
            ocol["תאריך קבלה"]: {"date": o.date} if o.date else None,
            ocol["סטטוס הזמנה"]: {"label": o.order_status},
            ocol["חיוב"]: {"label": o.billing} if o.billing else None,
            ocol["דחוף"]: {"checked": "true"} if o.urgent else None,
            ocol["פרויקט / אתר"]: o.project,
            ocol["ערוץ"]: {"label": "לא ידוע"},
            ocol["מס' במקור"]: o.num,
            ocol["הערות"]: {"text": o.notes} if o.notes else None,
            ocol["מה לבדוק"]: {"text": "\n".join(o.review)} if o.review else None,
        })
        oid = m.create_item(orders_board, f"{o.num} · {cname}", values)
        ln = o.line
        dims = f"{ln.width:g}x{ln.height:g}" if ln.width else (ln.dims_raw or "")
        m.create_subitem(oid, f"{ln.item_type} {dims}".strip(), compact({
            lcol["סוג פריט"]: {"labels": [ln.item_type]},
            lcol["רוחב (ס\"מ)"]: str(ln.width) if ln.width is not None else None,
            lcol["גובה (ס\"מ)"]: str(ln.height) if ln.height is not None else None,
            lcol["מידות במקור"]: ln.dims_raw,
            lcol["כמות"]: str(ln.qty) if ln.qty is not None else None,
            lcol["סופק"]: str(ln.delivered) if ln.delivered is not None else None,
            lcol["גוון"]: {"labels": [ln.color]} if ln.color else None,
            lcol["שלב"]: {"label": ln.stage} if ln.stage else None,
        }))
        created += 1
        print(f"  + הזמנה {o.num} ({cname})")
    print(f"\nנוצרו {created} הזמנות; {skipped_existing} כבר היו קיימות ודולגו.")


# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description="ייבוא הזמנות מתכת הגליל ל-monday")
    ap.add_argument("xlsx")
    ap.add_argument("--apply", action="store_true", help="לייבא בפועל ל-monday (ברירת מחדל: ריצה יבשה)")
    ap.add_argument("--workspace-id", default=os.environ.get("MONDAY_WORKSPACE_ID"))
    ap.add_argument("--api-version", default=os.environ.get("MONDAY_API_VERSION"),
                    help="למשל 2025-04. בלי ערך: גרסת ברירת המחדל של monday")
    ap.add_argument("--out", default=".", help="תיקייה לדוח ולקבצי הפלט")
    args = ap.parse_args()

    rows = read_rows(args.xlsx)
    orders, clients, skipped = clean(rows)

    os.makedirs(args.out, exist_ok=True)
    report = os.path.join(args.out, "import_report.md")
    write_report(report, orders, clients, skipped, args.xlsx)
    with open(os.path.join(args.out, "cleaned.json"), "w", encoding="utf-8") as f:
        json.dump({"clients": [asdict(c) for c in clients.values()],
                   "orders": [asdict(o) for o in orders],
                   "skipped": [asdict(x) for x in skipped]}, f, ensure_ascii=False, indent=2)
    print(f"נוקו {len(orders)} הזמנות, {len(clients)} לקוחות, {len(skipped)} שורות לא יובאו.")
    print(f"דוח: {report}")

    if not args.apply:
        print("ריצה יבשה. להרצה מול monday: --apply עם MONDAY_TOKEN.")
        return
    token = os.environ.get("MONDAY_TOKEN")
    if not token:
        sys.exit("חסר MONDAY_TOKEN בסביבה.")
    apply_to_monday(orders, clients, token, args.workspace_id, args.api_version,
                    os.path.join(args.out, "monday_state.json"))


if __name__ == "__main__":
    main()
