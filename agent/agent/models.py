"""Shared data types."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Attachment:
    filename: str
    media_type: str
    data: bytes


@dataclass
class IntakeMessage:
    """One incoming order, from any channel."""
    channel: str                       # מייל / וואטסאפ / הזמנת רכש / פורטל / טלפון
    text: str = ""
    received_at: str = ""              # ISO datetime. Relative dates ("סוף החודש") resolve against it
    sender_phone: str | None = None
    sender_email: str | None = None
    sender_name: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    known_client_id: str | None = None # from the portal: the client is already identified by the link
    draft_item_id: str | None = None   # from the portal: update this draft instead of creating a new one


@dataclass
class Contact:
    name: str
    phone: str | None  # normalized 0XXXXXXXXX


@dataclass
class Client:
    id: str
    name: str
    aliases: list[str]
    contacts: list[Contact]


@dataclass
class HistoryLine:
    item: str
    qty: float | None
    color: str | None
    width: float | None
    height: float | None
    stage: str | None = None       # שלב ייצור (לתשובות ללקוח)
    delivered: float | None = None


@dataclass
class HistoryOrder:
    id: str
    number: str
    date: str | None
    status: str | None
    lines: list[HistoryLine]
    due: str | None = None


@dataclass
class Candidate:
    client_id: str
    score: int
    evidence: list[str]


@dataclass
class Decision:
    status: str                       # פתוחה / לבדיקה
    reasons: list[str]                # why it needs review (empty = clean)
    notes: list[str]                  # assumptions and info worth keeping that don't block


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write: int = 0
    cache_read: int = 0
    turns: int = 0

    def add(self, u) -> None:
        self.input_tokens += getattr(u, "input_tokens", 0) or 0
        self.output_tokens += getattr(u, "output_tokens", 0) or 0
        self.cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0
        self.cache_read += getattr(u, "cache_read_input_tokens", 0) or 0
        self.turns += 1

    def cost_usd(self, prices: dict) -> float:
        return (self.input_tokens * prices["input"] + self.output_tokens * prices["output"]
                + self.cache_write * prices["cache_write"] + self.cache_read * prices["cache_read"]) / 1e6
