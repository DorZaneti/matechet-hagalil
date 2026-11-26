"""A mock Claude Messages API for local end-to-end testing only (no key, no network).

Flow: get_my_orders on the first call, then a reply built from the data that came back.
It's a fixed script, not a model. It's here to check the portal → agent → data → answer wiring.
  python scripts/mock_claude.py   then   ANTHROPIC_BASE_URL=http://localhost:4020 ANTHROPIC_API_KEY=x uvicorn ...
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        msgs = body["messages"]
        last = msgs[-1]["content"]
        tool_result = next((b for b in last if isinstance(b, dict) and b.get("type") == "tool_result"), None) \
            if isinstance(last, list) else None
        if tool_result is None:
            content = [{"type": "tool_use", "id": "toolu_a", "name": "get_my_orders", "input": {}}]
        else:
            orders = json.loads(tool_result["content"])
            active = [o for o in orders if o["status"] not in ("סופקה", "בוטלה")]
            parts = [f"הזמנה {o['order']}: {o['items'][0]['item']} – {o['items'][0]['stage']}" for o in active[:3]]
            content = [{"type": "tool_use", "id": "toolu_b", "name": "reply", "input": {
                "answer": "(תשובת בדיקה) " + "; ".join(parts) + ". תאריך אספקה עוד לא נקבע, רינה תעדכן.",
                "needs_human": False, "orders_mentioned": [o["order"] for o in active[:3]]}}]
        out = {"id": "msg_x", "type": "message", "role": "assistant", "model": body["model"], "content": content,
               "stop_reason": "tool_use", "stop_sequence": None,
               "usage": {"input_tokens": 1500, "output_tokens": 120}}
        data = json.dumps(out, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", 4020), H).serve_forever()
