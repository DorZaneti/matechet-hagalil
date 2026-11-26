"""The full order path: identify client, extract (agent), validate, build the monday plan, write."""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import CHANNELS, COLS, DEFAULT_MODEL
from .llm import extract
from .matching import find_candidates
from .models import Decision, IntakeMessage, Usage
from .validate import decide


@dataclass
class Result:
    extraction: dict
    decision: Decision
    plan: dict
    usage: Usage
    trace: list = field(default_factory=list)
    item_id: str | None = None
    client_name: str | None = None


def build_plan(ex: dict, decision: Decision, msg: IntakeMessage, client_name: str | None, number: str,
               model: str) -> dict:
    o, l = COLS["orders"], COLS["lines"]
    cid = ex["client"]["client_id"]
    notes = [f"מקור ({msg.channel}):\n{msg.text.strip()}" if msg.text.strip() else f"מקור ({msg.channel}): קובץ מצורף"]
    if msg.attachments:
        notes.append("קבצים: " + ", ".join(a.filename for a in msg.attachments))
    if decision.notes:
        notes.append("הערות הסוכן:\n- " + "\n- ".join(decision.notes))
    if ex.get("split_delivery_allowed"):
        notes.append("הלקוח מאשר אספקה במנות")
    if ex.get("question_to_customer"):
        notes.append(f"שאלה מוצעת ללקוח: {ex['question_to_customer']}")

    cols = {
        o["status"]: {"label": decision.status},
        o["channel"]: {"label": msg.channel if msg.channel in CHANNELS else "לא ידוע"},
        o["received"]: {"date": msg.received_at[:10]},
        o["number"]: number,
        o["notes"]: {"text": "\n\n".join(notes)[:9000]},
        o["source"]: f"agent ({model})",
    }
    if cid:
        cols[o["client"]] = {"item_ids": [int(cid)]}
    if ex.get("contact_name") or msg.sender_name:
        cols[o["contact"]] = ex.get("contact_name") or msg.sender_name
    if msg.sender_phone:
        from .matching import normalize_phone
        p = normalize_phone(msg.sender_phone)
        if p:
            cols[o["phone"]] = {"phone": "+972" + p[1:], "countryShortName": "IL"}
    if ex.get("requested_date"):
        cols[o["due"]] = {"date": ex["requested_date"]}
    if ex.get("urgent"):
        cols[o["urgent"]] = {"checked": "true"}
    if ex.get("project_site"):
        cols[o["project"]] = ex["project_site"]
    if ex.get("customer_po_number"):
        cols[o["po"]] = ex["customer_po_number"]
    if decision.reasons:
        cols[o["review"]] = {"text": "\n".join(f"• {r}" for r in decision.reasons)}

    lines = []
    for x in ex.get("lines") or []:
        w, h = x.get("width_cm"), x.get("height_cm")
        dims = f"{w:g}x{h:g}" if w is not None and h is not None else "מידות חסרות"
        lc = {l["type"]: {"labels": [x["item_type"]]}, l["dims_raw"]: x.get("source_text", "")[:250],
              l["stage"]: {"label": "ממתין"}}
        if w is not None:
            lc[l["width"]] = str(w)
        if h is not None:
            lc[l["height"]] = str(h)
        if x.get("quantity") is not None:
            lc[l["qty"]] = str(x["quantity"])
        if x.get("finish"):
            lc[l["color"]] = {"labels": [x["finish"]]}
        lines.append({"name": f"{x['item_type']} {dims}", "columns": lc})

    who = client_name or "לקוח לא מזוהה"
    return {"name": f"{number} · {who}", "columns": cols, "lines": lines}


def process(msg: IntakeMessage, store, *, writer=None, llm_client=None, model: str = DEFAULT_MODEL) -> Result:
    """store: Monday or Snapshot (reading). writer: Monday, or None for a dry run that writes nothing."""
    clients = store.clients()
    by_id = {c.id: c for c in clients}
    candidates = find_candidates(clients, " ".join(filter(None, [msg.text, msg.sender_email])),
                                 msg.sender_phone, msg.sender_name)
    histories: dict[str, list] = {}

    def get_history(cid: str):
        if cid not in histories:
            histories[cid] = store.history(cid)
        return histories[cid]

    ex, usage, trace = extract(msg, clients, candidates, get_history, client=llm_client, model=model)
    cid = msg.known_client_id or ex["client"]["client_id"]
    history = get_history(cid) if cid in by_id else []
    decision = decide(ex, msg, clients, candidates, history)

    cid = ex["client"]["client_id"]
    client_name = by_id[cid].name if cid in by_id else None
    number = store.next_order_number()
    plan = build_plan(ex, decision, msg, client_name, number, model)
    item_id = writer.write_order(plan=plan, draft_item_id=msg.draft_item_id) if writer else None
    return Result(ex, decision, plan, usage, trace, item_id, client_name)
