"""Tests for everything that doesn't need an API key.

FakeClaude returns the responses a model would plausibly return (fixtures). They're here to check
the loop, the validation and the monday plan. They are not model results: those come from eval/run_eval.py.
"""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import COLS  # noqa: E402
from agent.llm import RECORD_ORDER_SCHEMA, TOOLS  # noqa: E402
from agent.matching import find_candidates, normalize_phone, strength  # noqa: E402
from agent.models import IntakeMessage  # noqa: E402
from agent.monday import Snapshot  # noqa: E402
from agent.pipeline import process  # noqa: E402
from eval.examples import AB, EXAMPLES, RECEIVED_AT, ROTEM, SG  # noqa: E402

STORE = Snapshot(str(ROOT / "eval" / "snapshot.json"))
CLIENTS = STORE.clients()


def line(t, w, h, q, fin, src="", hist=False, conf="high", issues=()):
    return {"item_type": t, "width_cm": w, "height_cm": h, "quantity": q, "finish": fin, "source_text": src,
            "derived_from_history": hist, "confidence": conf, "issues": list(issues)}


def record(client_id, conf, lines, date=None, missing=(), **kw):
    base = {"client": {"client_id": client_id, "name_as_written": None, "evidence": "x", "confidence": conf},
            "contact_name": None, "lines": lines, "requested_date": date, "requested_date_text": None,
            "date_interpretation": None, "urgent": False, "project_site": None, "customer_po_number": None,
            "split_delivery_allowed": None, "missing_or_unclear": list(missing), "assumptions": [],
            "question_to_customer": None}
    base.update(kw)
    return base


FIXTURES = {
    1: record(ROTEM, "high", [line("מעקה מרפסת", 120, 100, 36, "RAL 7016"), line("מעקה מרפסת", 180, 100, 4, "RAL 7016")],
              "2026-11-30", missing=["כתוב 'מצורפת הזמנה' אבל לא צורף קובץ"], split_delivery_allowed=True,
              project_site="האלונים, עפולה, בניין B", requested_date_text="סוף החודש", date_interpretation="היום האחרון בנובמבר"),
    2: record(AB, "medium", [line("שער חניה", 500, 180, 1, "RAL 9005", hist=True,
                                  issues=["נבנה מהזמנה 1042 (400x180) עם תוספת מטר ברוחב", "קוד RAL הוסק מ'שחור'"])],
              "2026-12-03", urgent=True, requested_date_text="לשבוע הבא", date_interpretation="יום חמישי בשבוע הבא"),
    3: record(SG, "high", [line("מסגרת פלדה", 200, 300, 8, "מגולוון"), line("מסגרת פלדה", 250, 300, 4, "מגולוון")],
              "2026-12-15", customer_po_number="2026-118", project_site="אתר מגדלי העמק, יקנעם"),
    4: record(None, "low", [line("מעקה מדרגות", None, 90, None, "RAL 9005", conf="medium",
                                 issues=["קוד RAL הוסק מ'שחור'"])],
              None, missing=["לא מופיע שם לקוח", "חסר אורך המעקה", "לא צוינה כמות"],
              question_to_customer="היי, קיבלנו סקיצה של מעקה מדרגות. ממי ההזמנה, מה האורך וכמה יחידות?"),
}


class FakeClaude:
    """Records the requests and returns a scripted sequence of responses."""

    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=lambda o: o.__dict__)))
        blocks = self.script.pop(0)
        return NS(content=blocks, usage=NS(input_tokens=3000, output_tokens=400,
                                           cache_creation_input_tokens=0, cache_read_input_tokens=0))


def tool(name, inp, i="t1"):
    return NS(type="tool_use", id=i, name=name, input=inp)


def msg_for(ex):
    return IntakeMessage(channel=ex["channel"], text=ex["text"], received_at=RECEIVED_AT)


class TestMatching(unittest.TestCase):
    def test_phone(self):
        self.assertEqual(normalize_phone("+972 50-123-4567"), "0501234567")
        self.assertEqual(normalize_phone("04-8123456"), "048123456")
        self.assertIsNone(normalize_phone("123"))

    def test_examples(self):
        exp = {1: (ROTEM, "strong"), 2: (AB, "weak"), 3: (SG, "strong"), 4: (None, "none")}
        for ex in EXAMPLES:
            c = find_candidates(CLIENTS, ex["text"])
            want_id, want_strength = exp[ex["id"]]
            self.assertEqual(c[0].client_id if c else None, want_id, ex["id"])
            self.assertEqual(strength(c), want_strength, ex["id"])

    def test_phone_beats_name(self):
        c = find_candidates(CLIENTS, "שלום, מוטי כאן", sender_phone="052-7654321")
        self.assertEqual(c[0].client_id, ROTEM)  # the phone belongs to Sahar (Rotem), even though "מוטי" is written


class TestSchema(unittest.TestCase):
    def test_strict_rules(self):
        """Strict mode requires additionalProperties false and required = all fields, at every level."""
        def walk(s, path="root"):
            if "anyOf" in s:
                for x in s["anyOf"]:
                    walk(x, path)
                return
            if s.get("type") == "object":
                self.assertIs(s.get("additionalProperties"), False, path)
                self.assertEqual(set(s["required"]), set(s["properties"]), path)
                for k, v in s["properties"].items():
                    walk(v, f"{path}.{k}")
            if s.get("type") == "array":
                walk(s["items"], path + "[]")
            for bad in ("minimum", "maximum", "minLength", "maxLength", "oneOf"):
                self.assertNotIn(bad, s, path)
        for t in TOOLS:
            self.assertTrue(t["strict"])
            walk(t["input_schema"], t["name"])
        walk(RECORD_ORDER_SCHEMA)


class TestPipeline(unittest.TestCase):
    def run_example(self, n, script):
        fake = FakeClaude(script)
        ex = next(e for e in EXAMPLES if e["id"] == n)
        return process(msg_for(ex), STORE, llm_client=fake), fake

    def test_example2_uses_history_tool_and_goes_to_review(self):
        r, fake = self.run_example(2, [[tool("get_client_orders", {"client_id": AB})],
                                       [tool("record_order", FIXTURES[2], "t2")]])
        # the tool returned the history, and the model saw 1042 400x180
        tool_result = fake.calls[1]["messages"][2]["content"][0]
        self.assertEqual(tool_result["type"], "tool_result")
        hist = json.loads(tool_result["content"])
        self.assertIn({"item": "שער חניה", "width_cm": 400.0, "height_cm": 180.0, "qty": 1.0, "finish": "RAL 9005"},
                      [l for o in hist for l in o["lines"]])
        self.assertEqual(r.decision.status, "לבדיקה")
        joined = " ".join(r.decision.reasons)
        self.assertIn("ראיה חלשה", joined)          # only a first name
        self.assertIn("נבנתה מהזמנה קודמת", joined)
        self.assertEqual(r.usage.turns, 2)
        self.assertEqual([t["tool"] for t in r.trace], ["get_client_orders", "record_order"])

    def test_request_shape(self):
        _, fake = self.run_example(3, [[tool("record_order", FIXTURES[3])]])
        req = fake.calls[0]
        self.assertEqual(req["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertIn("ש.ג. עבודות עפר", req["system"][0]["text"])
        self.assertIn("2026-11-26", req["system"][0]["text"])
        self.assertTrue(all(t["strict"] for t in req["tools"]))
        user_text = " ".join(b.get("text", "") for b in req["messages"][0]["content"])
        self.assertIn("מועמדים מהתאמה דטרמיניסטית: " + SG, user_text)

    def test_example1_review_because_of_missing_attachment(self):
        r, _ = self.run_example(1, [[tool("record_order", FIXTURES[1])]])
        self.assertEqual(r.decision.status, "לבדיקה")
        self.assertEqual(r.decision.reasons, ["כתוב 'מצורפת הזמנה' אבל לא צורף קובץ"])

    def test_example1_clean_if_model_had_not_flagged(self):
        clean = dict(FIXTURES[1], missing_or_unclear=[])
        r, _ = self.run_example(1, [[tool("record_order", clean)]])
        self.assertEqual(r.decision.status, "פתוחה")

    def test_example3_open_with_cancelled_note(self):
        r, _ = self.run_example(3, [[tool("record_order", FIXTURES[3])]])
        self.assertEqual(r.decision.status, "פתוחה", r.decision.reasons)
        self.assertTrue(any("1048" in n and "בוטלה" in n for n in r.decision.notes))
        cols = r.plan["columns"]
        o, l = COLS["orders"], COLS["lines"]
        self.assertEqual(cols[o["client"]], {"item_ids": [int(SG)]})
        self.assertEqual(cols[o["po"]], "2026-118")
        self.assertEqual(cols[o["due"]], {"date": "2026-12-15"})
        self.assertEqual(r.plan["name"], "1051 · ש.ג. עבודות עפר")
        self.assertEqual([x["name"] for x in r.plan["lines"]], ["מסגרת פלדה 200x300", "מסגרת פלדה 250x300"])
        self.assertEqual(r.plan["lines"][0]["columns"][l["color"]], {"labels": ["מגולוון"]})

    def test_example4_unknown_client_review(self):
        r, _ = self.run_example(4, [[tool("record_order", FIXTURES[4])]])
        self.assertEqual(r.decision.status, "לבדיקה")
        joined = " ".join(r.decision.reasons)
        for want in ("לא זוהה לקוח", "חסרה כמות", "חסרות מידות", "לא צוין תאריך"):
            self.assertIn(want, joined)
        self.assertNotIn(COLS["orders"]["client"], r.plan["columns"])
        self.assertTrue(r.plan["name"].endswith("לקוח לא מזוהה"))

    def test_model_picks_wrong_client(self):
        wrong = dict(FIXTURES[3], client={**FIXTURES[3]["client"], "client_id": ROTEM})
        r, _ = self.run_example(3, [[tool("record_order", wrong)]])
        self.assertEqual(r.decision.status, "לבדיקה")
        self.assertIn("זיהוי הלקוח לא חד", r.decision.reasons[0])

    def test_model_invents_client_id(self):
        bad = dict(FIXTURES[3], client={**FIXTURES[3]["client"], "client_id": "999"})
        r, _ = self.run_example(3, [[tool("record_order", bad)]])
        self.assertEqual(r.decision.status, "לבדיקה")
        self.assertNotIn(COLS["orders"]["client"], r.plan["columns"])

    def test_duplicate_of_active_order(self):
        dup = record(AB, "high", [line("מעקה מרפסת", 120, 100, 40, "RAL 9005")], "2026-12-20")
        msg = IntakeMessage(channel="מייל", text="א.ב. בנייה: 40 מעקות מרפסת 120x100 RAL 9005", received_at=RECEIVED_AT)
        r = process(msg, STORE, llm_client=FakeClaude([[tool("record_order", dup)]]))
        self.assertTrue(any("חשד לכפילות" in x for x in r.decision.reasons))

    def test_text_answer_then_forced_tool(self):
        fake = FakeClaude([[NS(type="text", text="ok")], [tool("record_order", FIXTURES[3])]])
        r = process(msg_for(EXAMPLES[2]), STORE, llm_client=fake)
        self.assertEqual(fake.calls[1]["tool_choice"], {"type": "tool", "name": "record_order"})
        self.assertEqual(r.decision.status, "פתוחה")

    def test_portal_known_client_overrides(self):
        msg = IntakeMessage(channel="פורטל", text="8 מסגרות 200x300 מגולוון ל-15.12", received_at=RECEIVED_AT,
                            known_client_id=SG)
        noclient = dict(FIXTURES[3], client={**FIXTURES[3]["client"], "client_id": None})
        r = process(msg, STORE, llm_client=FakeClaude([[tool("record_order", noclient)]]))
        self.assertEqual(r.plan["columns"][COLS["orders"]["client"]], {"item_ids": [int(SG)]})


if __name__ == "__main__":
    unittest.main(verbosity=1)
