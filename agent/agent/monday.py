"""monday access: reading clients and history, writing orders and lines. Also a "snapshot" mode for running offline."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import BOARDS, COLS, TIMEZONE
from .matching import normalize_phone
from .models import Client, Contact, HistoryLine, HistoryOrder

API = "https://api.monday.com/v2"


class MondayError(RuntimeError):
    pass


class Monday:
    def __init__(self, token: str | None = None, session=None):
        import requests
        self.s = session or requests.Session()
        self.token = token if token is not None else os.environ.get("MONDAY_TOKEN")
        self.headers = {"Content-Type": "application/json", "API-Version": "2025-04"}
        if self.token:
            self.headers["Authorization"] = self.token

    def q(self, query: str, variables: dict | None = None) -> dict:
        for attempt in range(4):
            r = self.s.post(API, headers=self.headers, json={"query": query, "variables": variables or {}}, timeout=60)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            body = r.json()
            if body.get("errors") or body.get("error_message"):
                msg = json.dumps(body.get("errors") or body.get("error_message"), ensure_ascii=False)
                if "Complexity" in msg:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise MondayError(msg)
            return body["data"]
        raise MondayError("monday: retries exhausted")

    # ---------- read ----------
    def clients(self) -> list[Client]:
        c = COLS["clients"]
        data = self.q(
            "query ($b: [ID!]) { boards(ids: $b) { items_page(limit: 500) { items { id name "
            "column_values(ids: [\"%s\", \"%s\", \"%s\", \"%s\"]) { id text } } } } }"
            % (c["contact"], c["phone"], c["contacts"], c["aliases"]),
            {"b": [BOARDS["clients"]]},
        )
        return [_client_from_item(i) for i in data["boards"][0]["items_page"]["items"]]

    def history(self, client_id: str, limit: int = 10) -> list[HistoryOrder]:
        rel = COLS["clients"]["orders"]
        d = self.q("query ($i: [ID!]) { items(ids: $i) { column_values(ids: [\"%s\"]) "
                   "{ ... on BoardRelationValue { linked_item_ids } } } }" % rel, {"i": [client_id]})
        items = d["items"]
        ids = items[0]["column_values"][0].get("linked_item_ids", []) if items else []
        if not ids:
            return []
        o, l = COLS["orders"], COLS["lines"]
        d = self.q(
            "query ($i: [ID!]) { items(ids: $i, limit: 100) { id name column_values(ids: [\"%s\", \"%s\", \"%s\", \"%s\"]) { id text } "
            "subitems { name column_values(ids: [\"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"%s\"]) { id text } } } }"
            % (o["number"], o["received"], o["status"], o["due"], l["type"], l["width"], l["height"], l["qty"], l["color"],
               l["stage"], l["delivered"]),
            {"i": ids},
        )
        orders = [_history_from_item(i) for i in d["items"]]
        return sorted(orders, key=lambda x: x.date or "", reverse=True)[:limit]

    def next_order_number(self) -> str:
        col = COLS["orders"]["number"]
        d = self.q("query ($b: [ID!]) { boards(ids: $b) { items_page(limit: 500) { items { column_values(ids: [\"%s\"]) { text } } } } }"
                   % col, {"b": [BOARDS["orders"]]})
        nums = [int(cv["text"]) for i in d["boards"][0]["items_page"]["items"]
                for cv in i["column_values"] if cv["text"] and cv["text"].isdigit()]
        return str(max(nums, default=1050) + 1)

    def draft(self, item_id: str) -> dict:
        o = COLS["orders"]
        d = self.q("query ($i: [ID!]) { items(ids: $i) { id name column_values(ids: [\"%s\", \"%s\"]) { id text value } } }"
                   % (o["notes"], o["files"]), {"i": [item_id]})
        if not d["items"]:
            raise MondayError(f"draft {item_id} not found")
        it = d["items"][0]
        cv = {c["id"]: c for c in it["column_values"]}
        text = (cv[o["notes"]]["text"] or "").removeprefix("מהפורטל:").strip()
        files = []
        raw = cv[o["files"]].get("value")
        if raw:
            asset_ids = [f["assetId"] for f in json.loads(raw).get("files", []) if "assetId" in f]
            if asset_ids:
                a = self.q("query ($a: [ID!]!) { assets(ids: $a) { name public_url } }", {"a": asset_ids})
                files = a["assets"]
        return {"text": text, "files": files}

    # ---------- write ----------
    def write_order(self, *, plan: dict, draft_item_id: str | None = None) -> str:
        """plan = {"name", "columns": {...}, "lines": [{"name", "columns"}]}. Returns the order item id."""
        cols = json.dumps(plan["columns"], ensure_ascii=False)
        if draft_item_id:
            self.q("mutation ($b: ID!, $i: ID!, $v: JSON!) { change_multiple_column_values(board_id: $b, item_id: $i, "
                   "column_values: $v, create_labels_if_missing: true) { id } }",
                   {"b": BOARDS["orders"], "i": draft_item_id, "v": cols})
            self.q("mutation ($b: ID!, $i: ID!, $v: JSON!) { change_multiple_column_values(board_id: $b, item_id: $i, "
                   "column_values: $v) { id } }",
                   {"b": BOARDS["orders"], "i": draft_item_id, "v": json.dumps({"name": plan["name"]}, ensure_ascii=False)})
            item_id = draft_item_id
        else:
            item_id = self.q("mutation ($b: ID!, $n: String!, $v: JSON) { create_item(board_id: $b, item_name: $n, "
                             "column_values: $v, create_labels_if_missing: true) { id } }",
                             {"b": BOARDS["orders"], "n": plan["name"], "v": cols})["create_item"]["id"]
        for line in plan["lines"]:
            self.q("mutation ($p: ID!, $n: String!, $v: JSON) { create_subitem(parent_item_id: $p, item_name: $n, "
                   "column_values: $v, create_labels_if_missing: true) { id } }",
                   {"p": item_id, "n": line["name"], "v": json.dumps(line["columns"], ensure_ascii=False)})
        return item_id


class Snapshot:
    """Offline read-only stand-in for Monday, loaded from eval/snapshot.json (taken from the real boards)."""

    def __init__(self, path: str):
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        self._clients = [Client(c["id"], c["name"], c["aliases"], [Contact(**ct) for ct in c["contacts"]])
                         for c in raw["clients"]]
        self._history = {cid: [HistoryOrder(o["id"], o["number"], o["date"], o["status"],
                                            [HistoryLine(**l) for l in o["lines"]], o.get("due")) for o in orders]
                         for cid, orders in raw["history"].items()}

    def clients(self) -> list[Client]:
        return self._clients

    def history(self, client_id: str, limit: int = 10) -> list[HistoryOrder]:
        return self._history.get(client_id, [])[:limit]

    def next_order_number(self) -> str:
        return "1051"


# ---------- parsing helpers ----------

def _num(t: str | None) -> float | None:
    try:
        return float(t) if t not in (None, "") else None
    except ValueError:
        return None


def _client_from_item(i: dict) -> Client:
    c = COLS["clients"]
    cv = {x["id"]: (x["text"] or "") for x in i["column_values"]}
    contacts = []
    for row in cv.get(c["contacts"], "").splitlines():
        m = re.match(r"^(.*?)\s*([+\d][\d\-\s]{7,})?$", row.strip())
        if m and m.group(1):
            contacts.append(Contact(m.group(1).strip(), normalize_phone(m.group(2))))
    if not contacts and cv.get(c["contact"]):
        contacts.append(Contact(cv[c["contact"]], normalize_phone(cv.get(c["phone"]))))
    aliases = [a.strip() for a in cv.get(c["aliases"], "").splitlines() if a.strip()]
    return Client(i["id"], i["name"], aliases, contacts)


def _history_from_item(i: dict) -> HistoryOrder:
    o, l = COLS["orders"], COLS["lines"]
    cv = {x["id"]: x["text"] for x in i["column_values"]}
    lines = []
    for s in i.get("subitems") or []:
        sv = {x["id"]: x["text"] for x in s["column_values"]}
        lines.append(HistoryLine(sv.get(l["type"]) or s["name"], _num(sv.get(l["qty"])), sv.get(l["color"]) or None,
                                 _num(sv.get(l["width"])), _num(sv.get(l["height"])),
                                 sv.get(l["stage"]) or None, _num(sv.get(l["delivered"]))))
    return HistoryOrder(i["id"], cv.get(o["number"]) or i["name"].split("·")[0].strip(),
                        cv.get(o["received"]) or None, cv.get(o["status"]) or None, lines, cv.get(o["due"]) or None)


def now_iso() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="minutes")
