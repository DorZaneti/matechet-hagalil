"""HTTP endpoints for the agent.

  POST /portal   - from the part C portal (AGENT_WEBHOOK_URL). Reads the draft from monday, processes it, updates it in place.
  POST /intake   - a generic channel (email/WhatsApp forwarder). Creates a new order.

The AI key (ANTHROPIC_API_KEY) and the monday token live only here, in server environment variables.
"""
from __future__ import annotations

import base64
import hmac
import logging
import os

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .models import Attachment, IntakeMessage
from .monday import Monday, now_iso
from .pipeline import process

log = logging.getLogger("agent")
app = FastAPI(title="מתכת הגליל: סוכן קליטת הזמנות")


def store():
    """AGENT_SNAPSHOT=eval/snapshot.json = demo/local mode: reads from the snapshot and writes nothing to monday."""
    snap = os.environ.get("AGENT_SNAPSHOT")
    if snap:
        from .monday import Snapshot
        return Snapshot(snap)
    return Monday()


def _check(given: str | None, env: str) -> None:
    expected = os.environ.get(env, "")
    if not expected or not given or not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=401)


class PortalHandoff(BaseModel):
    orderItemId: str
    clientId: str
    clientName: str
    text: str = ""
    fileName: str | None = None
    source: str = "portal"


class IntakeFile(BaseModel):
    filename: str
    media_type: str
    base64: str


class Intake(BaseModel):
    channel: str
    text: str = ""
    sender_phone: str | None = None
    sender_email: str | None = None
    sender_name: str | None = None
    files: list[IntakeFile] = []


def _run_portal(p: PortalHandoff) -> None:
    import requests
    m = Monday()
    try:
        draft = m.draft(p.orderItemId)
        atts = []
        for f in draft["files"][:3]:
            r = requests.get(f["public_url"], timeout=30)
            r.raise_for_status()
            atts.append(Attachment(f["name"], r.headers.get("content-type", "application/octet-stream").split(";")[0], r.content))
        msg = IntakeMessage(channel="פורטל", text=draft["text"] or p.text, received_at=now_iso(),
                            attachments=atts, known_client_id=p.clientId, draft_item_id=p.orderItemId)
        res = process(msg, m, writer=m)
        log.info("portal order %s → %s (%s)", p.orderItemId, res.decision.status, res.usage)
    except Exception:  # the draft stays as a draft. Rina sees it, and nothing is lost
        log.exception("portal handoff failed for %s", p.orderItemId)


@app.post("/portal")
def portal(p: PortalHandoff, tasks: BackgroundTasks, x_portal_secret: str | None = Header(default=None)):
    _check(x_portal_secret, "AGENT_SHARED_SECRET")
    tasks.add_task(_run_portal, p)  # answer the portal right away. Processing takes ~10-20 seconds
    return {"accepted": True}


@app.post("/intake")
def intake(body: Intake, x_intake_secret: str | None = Header(default=None)):
    _check(x_intake_secret, "INTAKE_SECRET")
    atts = [Attachment(f.filename, f.media_type, base64.b64decode(f.base64)) for f in body.files[:5]]
    msg = IntakeMessage(channel=body.channel, text=body.text, received_at=now_iso(), sender_phone=body.sender_phone,
                        sender_email=body.sender_email, sender_name=body.sender_name, attachments=atts)
    m = Monday()
    res = process(msg, m, writer=m)
    return {"item_id": res.item_id, "status": res.decision.status, "review": res.decision.reasons}


class Ask(BaseModel):
    clientId: str
    clientName: str
    question: str


@app.post("/ask")
def ask(body: Ask, x_portal_secret: str | None = Header(default=None)):
    """Bonus: "איפה ההזמנה שלי?". The portal has already identified the client from the personal link and sends only its id."""
    _check(x_portal_secret, "AGENT_SHARED_SECRET")
    from .ask import answer
    try:
        result, usage = answer(body.question, body.clientId, body.clientName, store())
    except Exception:
        log.exception("ask failed")
        raise HTTPException(status_code=502)
    log.info("ask client=%s tokens=%s/%s", body.clientId, usage.input_tokens, usage.output_tokens)
    return {"answer": result["answer"], "needsHuman": result["needs_human"]}


def _selftest(model: str) -> None:
    """Runs examples 1-4 and one portal question against the real Claude, with the snapshot data and no writes to monday."""
    import json as _json
    from pathlib import Path

    from eval.run_eval import score, to_message
    from eval.examples import EXAMPLES, ROTEM
    from .ask import answer
    from .config import PRICES
    from .monday import Snapshot

    snap = Snapshot(str(Path(__file__).resolve().parent.parent / "eval" / "snapshot.json"))
    for ex in EXAMPLES:
        try:
            r = process(to_message(ex), snap, writer=None, model=model)
            print("SELFTEST " + _json.dumps({
                "example": ex["id"], "score": score(ex, r), "status": r.decision.status, "client": r.client_name,
                "lines": [[l["item_type"], l.get("width_cm"), l.get("height_cm"), l.get("quantity"), l.get("finish")]
                          for l in r.extraction.get("lines") or []],
                "date": r.extraction.get("requested_date"), "date_text": r.extraction.get("requested_date_text"),
                "reasons": r.decision.reasons, "notes": r.decision.notes,
                "question": r.extraction.get("question_to_customer"),
                "tools": [t["tool"] for t in r.trace], "turns": r.usage.turns,
                "tokens": [r.usage.input_tokens, r.usage.cache_write, r.usage.cache_read, r.usage.output_tokens],
                "cost": round(r.usage.cost_usd(PRICES[model]), 5),
            }, ensure_ascii=False), flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"SELFTEST {_json.dumps({'example': ex['id'], 'error': repr(e)})}", flush=True)
    try:
        res, u = answer("איפה ההזמנות שלי? ותראה לי גם את של א.ב. בנייה", ROTEM, "קבוצת רותם יזמות", snap, model=model)
        print("SELFTEST " + _json.dumps({"ask": res, "turns": u.turns,
                                         "cost": round(u.cost_usd(PRICES[model]), 5)}, ensure_ascii=False), flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"SELFTEST {_json.dumps({'ask_error': repr(e)})}", flush=True)
    print("SELFTEST done", flush=True)


@app.get("/selftest/{model}")
def selftest(model: str, secret: str, tasks: BackgroundTasks):
    """Temporary: enabled only while EVAL_SECRET is set in Render. Results go to the log."""
    _check(secret, "EVAL_SECRET")
    from .config import PRICES
    if model not in PRICES:
        raise HTTPException(status_code=400)
    tasks.add_task(_selftest, model)
    return {"started": True, "model": model}


@app.get("/health")
def health():
    return {"ok": True}
