"""Extraction with Claude: an agent loop with two tools.

  get_client_orders(client_id)  - pulls the client's recent orders (needed for "כמו פעם שעברה")
  record_order(...)             - the final answer. strict: true, so the output always matches the schema

The model extracts and flags. It does not decide the status: validate.py does that with deterministic rules.
"""
from __future__ import annotations

import base64
import io
import json
import zipfile
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from .config import DEFAULT_MODEL, ITEM_TYPES, MAX_AGENT_TURNS, TIMEZONE
from .models import Attachment, Candidate, Client, HistoryOrder, IntakeMessage, Usage

NULLABLE = lambda schema: {"anyOf": [schema, {"type": "null"}]}  # noqa: E731
CONF = {"type": "string", "enum": ["high", "medium", "low"]}

RECORD_ORDER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["client", "contact_name", "lines", "requested_date", "requested_date_text",
                 "date_interpretation", "urgent", "project_site", "customer_po_number",
                 "split_delivery_allowed", "missing_or_unclear", "assumptions", "question_to_customer"],
    "properties": {
        "client": {
            "type": "object",
            "additionalProperties": False,
            "required": ["client_id", "name_as_written", "evidence", "confidence"],
            "properties": {
                "client_id": NULLABLE({"type": "string"}),
                "name_as_written": NULLABLE({"type": "string"}),
                "evidence": {"type": "string"},
                "confidence": CONF,
            },
        },
        "contact_name": NULLABLE({"type": "string"}),
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["item_type", "width_cm", "height_cm", "quantity", "finish", "source_text",
                             "derived_from_history", "confidence", "issues"],
                "properties": {
                    "item_type": {"type": "string", "enum": ITEM_TYPES},
                    "width_cm": NULLABLE({"type": "number"}),
                    "height_cm": NULLABLE({"type": "number"}),
                    "quantity": NULLABLE({"type": "integer"}),
                    "finish": NULLABLE({"type": "string"}),
                    "source_text": {"type": "string"},
                    "derived_from_history": {"type": "boolean"},
                    "confidence": CONF,
                    "issues": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "requested_date": NULLABLE({"type": "string", "format": "date"}),
        "requested_date_text": NULLABLE({"type": "string"}),
        "date_interpretation": NULLABLE({"type": "string"}),
        "urgent": {"type": "boolean"},
        "project_site": NULLABLE({"type": "string"}),
        "customer_po_number": NULLABLE({"type": "string"}),
        "split_delivery_allowed": NULLABLE({"type": "boolean"}),
        "missing_or_unclear": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "question_to_customer": NULLABLE({"type": "string"}),
    },
}

TOOLS = [
    {
        "name": "get_client_orders",
        "description": "Returns the recent orders of one client (number, date, status, lines with item, size, quantity, finish). "
                       "Call it only when the message refers to a previous order (e.g. 'כמו פעם שעברה', 'אותו דבר') "
                       "or when you need history to check for a duplicate.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["client_id"],
            "properties": {"client_id": {"type": "string"}},
        },
    },
    {
        "name": "record_order",
        "description": "Record the extracted order. Call exactly once, as the final step.",
        "strict": True,
        "input_schema": RECORD_ORDER_SCHEMA,
    },
]

SYSTEM_TEMPLATE = """You are the order-intake agent of "מתכת הגליל", a steel factory in northern Israel that makes
railings, gates and steel frames for contractors. Orders arrive as Hebrew emails, WhatsApp messages, purchase-order PDFs
and photos of hand sketches. Your job is to turn one incoming order into structured order lines, and to say clearly
what is missing or uncertain. A person (Rina, the office manager) reviews anything you flag. A wrong order that
looks confident is far worse than an order sent to review.

RULES
1. Never invent a value. If a size, quantity, finish, client or date is not stated, put null and explain in
   missing_or_unclear. Do not fill gaps from "typical" values.
2. Client: choose client_id only from the client list below. Use the sender phone, company name (any spelling or alias),
   PO header, signature or contact name as evidence, and write that evidence. A first name alone that matches one
   contact is "medium" confidence at most. If no client fits, client_id is null.
3. Lines: one line per distinct item and size. item_type must be one of the enum values. Map: "מעקה" for a balcony
   -> מעקה מרפסת; stairs -> מעקה מדרגות; "שער" for a car/parking gate -> שער חניה; a pedestrian/entrance gate -> שער כניסה;
   "מסגרת" -> מסגרת פלדה. If the type is implied but not written for a line (e.g. "ו-4 מעקות 180x100" right after
   "36 מעקות מרפסת"), you may use the same type, and say so in that line's issues only if it is genuinely ambiguous.
4. Sizes are width x height in cm, as written ("120x100" -> width 120, height 100). If a size is written in meters,
   convert and note it. If the text says "לפי תכנית" or the drawing is not legible, leave sizes null.
5. finish: "RAL dddd" for a RAL code, "מגולוון" for galvanized, "ללא צבע" for unpainted. A color name without a code
   ("שחור", "אפור") is not a code: you may convert only שחור -> RAL 9005 and אנתרציט -> RAL 7016 (the factory's standard
   mapping), and you must add an issue saying the code was inferred from a name.
6. History: if the message refers to a previous order, call get_client_orders, find that order, and build the line from
   it with the requested change. Set derived_from_history = true and write in issues exactly which order you used and
   what you changed. Never guess history without calling the tool.
7. Dates: today is {today} ({weekday}), timezone Asia/Jerusalem, Israeli work week Sunday-Thursday. Resolve relative dates
   against the received time: "סוף החודש" = last day of the current month; "שבוע הבא" = Thursday of next week;
   "דחוף" alone is not a date. Put the original words in requested_date_text and how you resolved them in
   date_interpretation. If no date is mentioned, requested_date is null.
8. Put the customer's PO number, project/site/building and whether split delivery is allowed in their fields.
9. If a document is mentioned but not attached ("מצורפת הזמנה" with nothing attached), add that to missing_or_unclear.
10. question_to_customer: one short, polite Hebrew question that would resolve the open points, or null if none.
11. assumptions: harmless interpretations only (e.g. how a relative date was resolved). Anything that changes what gets
    manufactured or who it is for goes in missing_or_unclear or the line's issues, not here.
12. Keep missing_or_unclear and issues SHORT and only for blockers. The system already detects by itself, from your nulls
    and flags, a missing client, size, quantity, finish or date, and history-derived lines, so do not restate those.
    Use missing_or_unclear only for blockers the system cannot see (an attachment that is mentioned but missing,
    contradictions, illegible text). Optional information that is simply not given is NOT a blocker and must not be
    listed anywhere: PO number, split delivery, site/project, sender phone or email, contact name.
    Use a line's issues only for real ambiguity in that line (one short sentence each). Do not explain things that are
    clear from the text. An empty list is the normal case for a clear order.
13. Finish by calling record_order. Do not answer in plain text.

CLIENTS (id | name | other spellings | contacts)
{clients}
"""


def clients_block(clients: list[Client]) -> str:
    rows = []
    for c in clients:
        contacts = "; ".join(f"{ct.name} {ct.phone or ''}".strip() for ct in c.contacts) or "-"
        rows.append(f"{c.id} | {c.name} | {', '.join(c.aliases) or '-'} | {contacts}")
    return "\n".join(rows)


def history_payload(orders: list[HistoryOrder]) -> str:
    return json.dumps([
        {"order": o.number, "date": o.date, "status": o.status,
         "lines": [{"item": l.item, "width_cm": l.width, "height_cm": l.height, "qty": l.qty, "finish": l.color}
                   for l in o.lines]}
        for o in orders
    ], ensure_ascii=False)


def _attachment_blocks(att: Attachment) -> list[dict]:
    b64 = base64.standard_b64encode(att.data).decode()
    if att.media_type == "application/pdf":
        return [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
                 "title": att.filename}]
    if att.media_type in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        return [{"type": "image", "source": {"type": "base64", "media_type": att.media_type, "data": b64}}]
    if att.media_type.startswith("text/"):
        return [{"type": "text", "text": f"[קובץ {att.filename}]\n{att.data.decode('utf-8', 'replace')}"}]
    if att.filename.lower().endswith(".xlsx"):
        return [{"type": "text", "text": f"[קובץ Excel {att.filename}]\n{_xlsx_to_text(att.data)}"}]
    if att.filename.lower().endswith(".docx"):
        return [{"type": "text", "text": f"[קובץ Word {att.filename}]\n{_docx_to_text(att.data)}"}]
    return [{"type": "text", "text": f"[קובץ מצורף בפורמט שלא נתמך: {att.filename}. אין לו תוכן לקריאה]"}]


def _xlsx_to_text(data: bytes) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            if any(v is not None for v in row):
                out.append(" | ".join("" if v is None else str(v) for v in row))
    return "\n".join(out[:300])


def _docx_to_text(data: bytes) -> str:
    import re
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)[:20000]


def user_content(msg: IntakeMessage, candidates: list[Candidate], clients_by_id: dict[str, Client]) -> list[dict]:
    head = [
        f"ערוץ: {msg.channel}",
        f"התקבל: {msg.received_at}",
        f"טלפון שולח: {msg.sender_phone or 'לא ידוע'}",
        f"מייל שולח: {msg.sender_email or 'לא ידוע'}",
        f"שם שולח: {msg.sender_name or 'לא ידוע'}",
    ]
    if msg.known_client_id:
        c = clients_by_id.get(msg.known_client_id)
        head.append(f"הלקוח כבר זוהה בפורטל (קישור אישי): {msg.known_client_id} {c.name if c else ''}")
    if candidates:
        head.append("מועמדים מהתאמה דטרמיניסטית: " + "; ".join(
            f"{c.client_id} ({clients_by_id[c.client_id].name}): {', '.join(c.evidence)}" for c in candidates[:3]))
    else:
        head.append("מועמדים מהתאמה דטרמיניסטית: אין")
    blocks: list[dict] = [{"type": "text", "text": "\n".join(head)}]
    blocks.append({"type": "text", "text": f"תוכן ההודעה:\n{msg.text or '(אין טקסט)'}"})
    if not msg.attachments:
        blocks.append({"type": "text", "text": "קבצים מצורפים: אין"})
    for a in msg.attachments:
        blocks.extend(_attachment_blocks(a))
    return blocks


def _today(received_at: str) -> datetime:
    try:
        return datetime.fromisoformat(received_at).astimezone(ZoneInfo(TIMEZONE))
    except ValueError:
        return datetime.now(ZoneInfo(TIMEZONE))


HEB_DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def extract(msg: IntakeMessage, clients: list[Client], candidates: list[Candidate],
            get_history: Callable[[str], list[HistoryOrder]], client=None, model: str = DEFAULT_MODEL
            ) -> tuple[dict, Usage, list[dict]]:
    """Runs the loop. Returns (record_order input, usage, trace of tool calls)."""
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    today = _today(msg.received_at)
    system = [{
        "type": "text",
        "text": SYSTEM_TEMPLATE.format(today=today.date().isoformat(), weekday=f"יום {HEB_DAYS[today.weekday()]}",
                                       clients=clients_block(clients)),
        "cache_control": {"type": "ephemeral"},  # the client list repeats in every call; cache reads cost ~5% of input
    }]
    by_id = {c.id: c for c in clients}
    messages: list[dict] = [{"role": "user", "content": user_content(msg, candidates, by_id)}]
    usage, trace = Usage(), []
    tool_choice: dict = {"type": "auto"}

    for turn in range(MAX_AGENT_TURNS):
        # Not forcing a specific tool: some models reject tool_choice of type tool/any. Instead an explicit instruction
        resp = client.messages.create(model=model, max_tokens=2500, system=system, tools=TOOLS,
                                      tool_choice=tool_choice, messages=messages)
        usage.add(resp.usage)
        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        final = next((b for b in tool_uses if b.name == "record_order"), None)
        if final is not None:
            trace.append({"tool": "record_order"})
            return final.input, usage, trace
        if not tool_uses:  # answered in text: ask for the tool explicitly
            messages.append({"role": "user", "content": "Call record_order now with the result. Do not answer in text."})
            continue
        results = []
        for b in tool_uses:
            if b.name == "get_client_orders":
                cid = str(b.input.get("client_id", ""))
                if cid in by_id:
                    payload = history_payload(get_history(cid))
                else:
                    payload = json.dumps({"error": "unknown client_id"})
                trace.append({"tool": "get_client_orders", "client_id": cid})
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": payload})
            else:
                results.append({"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                                "content": "unknown tool"})
        if turn == MAX_AGENT_TURNS - 2:
            results.append({"type": "text", "text": "Now call record_order with the final result."})
        messages.append({"role": "user", "content": results})
    raise RuntimeError("agent did not call record_order")
