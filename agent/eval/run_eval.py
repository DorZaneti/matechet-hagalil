"""Runs the agent on examples 1-4 and writes eval/eval_results.md.

  export ANTHROPIC_API_KEY=...
  python eval/run_eval.py                         # offline: clients and history from eval/snapshot.json, writes nothing to monday
  python eval/run_eval.py --model claude-haiku-5-5
  MONDAY_TOKEN=... python eval/run_eval.py --live --write   # reads from monday and creates the orders there
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import DEFAULT_MODEL, PRICES  # noqa: E402
from agent.models import Attachment, IntakeMessage  # noqa: E402
from agent.monday import Monday, Snapshot  # noqa: E402
from agent.pipeline import process  # noqa: E402
from eval.examples import EXAMPLES, RECEIVED_AT  # noqa: E402


def to_message(ex: dict) -> IntakeMessage:
    atts = []
    if ex.get("image"):
        atts.append(Attachment(Path(ex["image"]).name, "image/png", Path(ex["image"]).read_bytes()))
    return IntakeMessage(channel=ex["channel"], text=ex["text"], received_at=RECEIVED_AT, attachments=atts)


def line_tuple(l: dict):
    return (l["item_type"], l.get("width_cm"), l.get("height_cm"), l.get("quantity"), l.get("finish"))


def score(ex: dict, r) -> dict:
    exp = ex["expected"]
    got_lines = sorted(line_tuple(l) for l in r.extraction.get("lines") or [])
    exp_lines = sorted(exp["lines"], key=lambda t: tuple(str(x) for x in t))
    got_lines = sorted(got_lines, key=lambda t: tuple(str(x) for x in t))
    return {
        "status": r.decision.status == exp["status"],
        "client": r.extraction["client"]["client_id"] == exp["client_id"],
        "lines": got_lines == exp_lines,
        "date": r.extraction.get("requested_date") == exp["date"],
    }


def fmt_line(t) -> str:
    item, w, h, q, fin = t
    size = f"{w:g}x{h:g}" if w is not None and h is not None else f"{'?' if w is None else f'{w:g}'}x{'?' if h is None else f'{h:g}'}"
    return f"{item} {size} · {q if q is not None else '?'} יח' · {fin or '?'}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--live", action="store_true", help="read clients/history from monday instead of the snapshot")
    ap.add_argument("--write", action="store_true", help="create the orders in monday (requires --live)")
    ap.add_argument("--only", type=int, nargs="*")
    args = ap.parse_args()

    store = Monday() if args.live else Snapshot(str(ROOT / "eval" / "snapshot.json"))
    writer = store if (args.write and args.live) else None
    prices = PRICES.get(args.model)

    rows, details, total = [], [], 0.0
    for ex in EXAMPLES:
        if args.only and ex["id"] not in args.only:
            continue
        print(f"→ example {ex['id']} ({ex['title']}) …", flush=True)
        r = process(to_message(ex), store, writer=writer, model=args.model)
        s = score(ex, r)
        cost = r.usage.cost_usd(prices) if prices else float("nan")
        total += cost
        mark = lambda ok: "✅" if ok else "❌"  # noqa: E731
        rows.append(f"| {ex['id']} {ex['title']} | {r.decision.status} {mark(s['status'])} | {r.client_name or '—'} {mark(s['client'])} "
                    f"| {len(r.extraction.get('lines') or [])} {mark(s['lines'])} | {r.extraction.get('requested_date') or '—'} {mark(s['date'])} "
                    f"| {r.usage.input_tokens + r.usage.cache_read + r.usage.cache_write:,} / {r.usage.output_tokens:,} | ${cost:.4f} |")
        tools = " → ".join(t["tool"] + (f"({t['client_id']})" if "client_id" in t else "") for t in r.trace)
        details.append("\n".join([
            f"### דוגמה {ex['id']}: {ex['title']}",
            f"**ציפייה:** {ex['expected']['status']}. {ex['expected']['why']}",
            f"**תוצאה:** {r.decision.status} · לקוח: {r.client_name or 'לא זוהה'} "
            f"({r.extraction['client']['confidence']}: {r.extraction['client']['evidence']})",
            f"**כלים:** {tools} · **סבבים:** {r.usage.turns}",
            "**שורות שחולצו:**",
            *[f"- {fmt_line(line_tuple(l))}" + (f" (issues: {'; '.join(l['issues'])})" if l.get("issues") else "")
              for l in r.extraction.get("lines") or []],
            "**שורות צפויות:**",
            *[f"- {fmt_line(t)}" for t in ex["expected"]["lines"]],
            f"**תאריך:** {r.extraction.get('requested_date') or '—'} "
            f"(\"{r.extraction.get('requested_date_text') or ''}\" · {r.extraction.get('date_interpretation') or ''})",
            "**מה לבדוק:**" if r.decision.reasons else "**מה לבדוק:** אין",
            *[f"- {x}" for x in r.decision.reasons],
            *(["**הערות:**", *[f"- {x}" for x in r.decision.notes]] if r.decision.notes else []),
            f"**שאלה ללקוח:** {r.extraction.get('question_to_customer') or '—'}",
            f"**נוצר ב-monday:** {r.item_id}" if r.item_id else "",
            "<details><summary>JSON מלא</summary>\n\n```json\n"
            + json.dumps(r.extraction, ensure_ascii=False, indent=1) + "\n```\n</details>",
        ]))

    out = ROOT / "eval" / "eval_results.md"
    out.write_text("\n".join([
        f"# תוצאות הרצה: {args.model}",
        f"מקור לקוחות/היסטוריה: {'monday חי' if args.live else 'snapshot.json'} · התקבל: {RECEIVED_AT}",
        "",
        "| דוגמה | סטטוס | לקוח | שורות | תאריך | טוקנים (קלט/פלט) | עלות |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *rows,
        "",
        f"**עלות כוללת:** ${total:.4f} · **ממוצע להזמנה:** ${total / max(len(rows), 1):.4f}",
        "",
        *details,
    ]) + "\n", encoding="utf-8")
    print(f"\n{out}")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
