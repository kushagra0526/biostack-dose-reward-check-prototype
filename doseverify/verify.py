"""Reward component: compare a candidate answer's structured items to the gold items.

reward = (matched − contradicted − unsupported orders) / required, clipped to [0, 1].
A gold field that is set must match exactly. A field the candidate leaves out counts as missing, not as a match.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, fields

from .parse import Finding, Order, parse


@dataclass
class Verdict:
    status: str  # PASS | FAIL | ABSTAIN (a required field couldn't be read: defer to an LLM judge / human)
    reward: float
    matched: list[str]
    contradicted: list[str]
    missing: list[str]
    unsupported: list[str]
    unreadable: list[str]


def _key(x) -> str:
    return x.drug if isinstance(x, Order) else x.finding


def _diff(gold, cand) -> tuple[list[str], list[str]]:
    """(hard conflicts: candidate states a different value, soft: candidate value couldn't be read)."""
    hard, soft = [], []
    for f in fields(gold):
        g, c = getattr(gold, f.name), getattr(cand, f.name)
        if f.name in ("prn", "per_kg", "present"):
            if g != c:
                hard.append(f"{f.name}: {c} (gold {g})")
        elif g is not None and g != c:
            (soft if c is None else hard).append(f"{f.name}: {c} (gold {g})")
    return hard, soft


def verify(candidate: str, gold: list) -> Verdict:
    cand = parse(candidate)
    text = candidate.lower()
    by = {}
    for c in cand:
        by.setdefault(_key(c), []).append(c)
    matched, contra, missing, unreadable = [], [], [], []
    for g in gold:
        cs = by.pop(_key(g), [])
        if not cs:
            (unreadable if _key(g) in text else missing).append(_key(g))
            continue
        diffs = [_diff(g, c) for c in cs]
        hard = [h for h, _ in diffs if h]
        soft = [s for _, s in diffs if s]
        if hard:
            contra.append(f"{_key(g)} — " + "; ".join(hard[0]))
        elif soft:
            unreadable.append(f"{_key(g)} — " + "; ".join(soft[0]))
        else:
            matched.append(_key(g))
    unsupported = [f"{k} (not in gold)" for k, cs in by.items() for c in cs if isinstance(c, Order) and c.action == "give"]
    n = len(gold)
    reward = max(0.0, (len(matched) - len(contra) - len(unsupported)) / n)
    status = "FAIL" if contra or unsupported or missing else "ABSTAIN" if unreadable else "PASS"
    return Verdict(status, round(reward, 4), matched, contra, missing, unsupported, unreadable)


# ------------------------------------------------------------------ baseline graders (surface similarity)

def _tok(s: str) -> list[str]:
    return re.findall(r"[a-z]+|\d+(?:\.\d+)?", s.lower())


def token_f1(candidate: str, reference: str, numbers: bool = True) -> float:
    a, b = _tok(candidate), _tok(reference)
    if not numbers:
        a, b = [t for t in a if not t[0].isdigit()], [t for t in b if not t[0].isdigit()]
    common = sum((Counter(a) & Counter(b)).values())
    if not common:
        return 0.0
    p, r = common / len(a), common / len(b)
    return 2 * p * r / (p + r)
