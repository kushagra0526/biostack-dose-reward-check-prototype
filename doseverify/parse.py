"""Parse free-text medication orders and imaging findings into structured, comparable items.

Doses are normalised to base units (mg, or "units" for insulin), frequencies to doses per day, durations to days,
so meaning-preserving rewrites compare equal and dose mutations don't.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DRUGS = ["amoxicillin", "metformin", "methotrexate", "apixaban", "enoxaparin", "levothyroxine", "vancomycin",
         "insulin glargine", "paracetamol", "morphine", "prednisone", "furosemide", "digoxin", "ceftriaxone",
         "colchicine", "folic acid", "ibuprofen", "warfarin", "aspirin", "metoprolol"]
FINDINGS = ["nodule", "pneumothorax", "pleural effusion", "stenosis", "consolidation", "fracture", "mass"]

UNIT_TO_MG = {"mg": 1.0, "mcg": 0.001, "µg": 0.001, "microgram": 0.001, "micrograms": 0.001, "g": 1000.0, "gram": 1000.0, "grams": 1000.0}
ROUTES = [(r"\b(po|orally|by mouth|oral)\b", "PO"), (r"\b(iv|intravenous(?:ly)?)\b", "IV"),
          (r"\b(sc|subcut(?:aneous(?:ly)?)?|sq)\b", "SC"), (r"\b(im|intramuscular(?:ly)?)\b", "IM")]
# phrase → doses per day ("once" = single dose)
FREQ = [(r"\b(once weekly|weekly|once a week|every week|q ?week)\b", 1 / 7),
        (r"\b(four times (?:a day|daily)|qid|every 6 hours|q6h)\b", 4),
        (r"\b(three times (?:a day|daily)|tid|every 8 hours|q8h)\b", 3),
        (r"\b(twice (?:a day|daily)|bid|bd|every 12 hours|q12h)\b", 2),
        (r"\b(every 4 hours|q4h)\b", 6),
        (r"\b(once daily|daily|every day|once a day|qd|od|every 24 hours|q24h|at bedtime|nightly|qhs)\b", 1),
        (r"\b(once|single dose|stat|one dose)\b", "once")]
NEG_ORDER = re.compile(r"\b(do not|don't|avoid|hold|stop|discontinue|withhold|no)\b")
NEG_FINDING = re.compile(r"\b(no|without|negative for|absent)\b")
NEG_AFTER = re.compile(r"\b(not seen|not present|not identified|absent|ruled out)\b")
SIDES = {"left": "left", "right": "right", "bilateral": "bilateral"}
SEVERITY = ["small", "mild", "moderate", "large", "severe"]
CLAUSE = re.compile(r"(?<!\d)\.(?!\d)|;|\n")


@dataclass(frozen=True)
class Order:
    drug: str
    action: str  # give | avoid
    dose: float | None = None  # in mg, or units for insulin
    unit: str | None = None  # mg | units
    per_kg: bool = False
    route: str | None = None
    per_day: float | str | None = None
    prn: bool = False
    days: int | None = None


@dataclass(frozen=True)
class Finding:
    finding: str
    present: bool
    side: str | None = None
    size_cm: float | None = None
    severity: str | None = None


def _num(s: str) -> float:
    return float(s)


def parse_clause(c: str):
    t = " " + c.lower().strip() + " "
    drug = next((d for d in DRUGS if re.search(rf"\b{d}\b", t)), None)
    if drug:
        before = t[: t.index(drug)]
        action = "avoid" if NEG_ORDER.search(before) else "give"
        dose = unit = None
        per_kg = False
        m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|µg|micrograms?|grams?|g|units?)\b(\s*/\s*kg|\s+per\s+kg)?", t)
        if m:
            v, u = _num(m.group(1)), m.group(2)
            if u.startswith("unit"):
                dose, unit = v, "units"
            else:
                dose, unit = round(v * UNIT_TO_MG[u], 6), "mg"
            per_kg = bool(m.group(3))
        route = next((r for p, r in ROUTES if re.search(p, t)), None)
        per_day = next((f for p, f in FREQ if re.search(p, t)), None)
        d = re.search(r"\b(?:for|x)\s*(\d+)\s*(days?|d|weeks?|wk)\b", t)
        days = (int(d.group(1)) * (7 if d.group(2).startswith("w") else 1)) if d else None
        prn = bool(re.search(r"\b(as needed|prn|when required)\b", t))
        return Order(drug, action, dose, unit, per_kg, route, per_day, prn, days)
    fnd = next((f for f in FINDINGS if re.search(rf"\b{f}\b", t)), None)
    if fnd:
        before = t[: t.index(fnd)]
        side = next((v for k, v in SIDES.items() if re.search(rf"\b{k}\b", t)), None)
        s = re.search(r"(\d+(?:\.\d+)?)\s*(cm|mm)\b", t)
        size = (round(_num(s.group(1)) / (10 if s.group(2) == "mm" else 1), 3)) if s else None
        sev = next((w for w in SEVERITY if re.search(rf"\b{w}\b", t)), None)
        after = t[t.index(fnd) + len(fnd):]
        return Finding(fnd, not (NEG_FINDING.search(before) or NEG_AFTER.search(after)), side, size, sev)
    return None


def parse(text: str) -> list:
    return [x for x in (parse_clause(c) for c in CLAUSE.split(text) if c.strip()) if x]
