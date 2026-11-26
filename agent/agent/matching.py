"""Deterministic client matching: no model involved.

The model also picks a client, but this is the check against it. If the two disagree, the order goes to review.
Same normalization as the import script from part B, so "א.ב. בנייה" and "אב בניה בע"מ" match.
"""
from __future__ import annotations

import re

from .models import Candidate, Client

GENERIC = {"קבוצת", "קבוצה", "חברת", "חברה", "בעמ"}


def normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    d = re.sub(r"\D", "", raw)
    if d.startswith("972"):
        d = "0" + d[3:]
    return d if re.fullmatch(r"0\d{8,9}", d) else None


def _norm_text(s: str) -> str:
    s = re.sub(r"[\"'״׳.\-–,()]", "", s)
    return s.replace("יי", "י").replace("וו", "ו")


def name_tokens(name: str) -> set[str]:
    return {w for w in _norm_text(name).split() if w and w not in GENERIC}


def _text_tokens(text: str) -> set[str]:
    toks = set()
    for w in _norm_text(text).split():
        toks.add(w)
        if len(w) > 2 and w[0] in "ובלמהש":  # Hebrew prefixes: "ולרותם", "מרותם"
            toks.add(w[1:])
    return toks


def find_candidates(clients: list[Client], text: str, sender_phone: str | None = None,
                    sender_name: str | None = None) -> list[Candidate]:
    """Scores: phone 5, company name or alias 3, full contact name 3, contact first name only 1."""
    phone = normalize_phone(sender_phone)
    blob = " ".join(filter(None, [text, sender_name]))
    words = _text_tokens(blob)
    out = []
    for c in clients:
        score, ev = 0, []
        if phone and any(ct.phone == phone for ct in c.contacts):
            score += 5
            ev.append(f"טלפון השולח {phone} שייך לאיש קשר של הלקוח")
        for n in [c.name, *c.aliases]:
            t = name_tokens(n)
            if t and t <= words:
                score += 3
                ev.append(f"שם הלקוח מופיע: '{n}'")
                break
        for ct in c.contacts:
            t = name_tokens(ct.name)
            if len(t) >= 2 and t <= words:
                score += 3
                ev.append(f"שם איש קשר מלא מופיע: '{ct.name}'")
                break
            first = ct.name.split()[0] if ct.name else ""
            if first and _norm_text(first) in words:
                score += 1
                ev.append(f"שם פרטי של איש קשר מופיע: '{first}'")
                break
        if score:
            out.append(Candidate(c.id, score, ev))
    return sorted(out, key=lambda x: -x.score)


def strength(candidates: list[Candidate]) -> str:
    """strong: one clear leader with real evidence. weak: only a first name, or a tie. none: nothing."""
    if not candidates:
        return "none"
    top = candidates[0]
    tie = len(candidates) > 1 and candidates[1].score == top.score
    if tie:
        return "weak"
    return "strong" if top.score >= 3 else "weak"
