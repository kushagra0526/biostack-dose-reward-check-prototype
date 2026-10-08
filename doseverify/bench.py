"""Synthetic gold cases, meaning-preserving paraphrases, and labelled harmful mutations (dose-specific and qualifier).

Gold doses are illustrative synthetic targets for testing a grader. They are not clinical guidance.
"""
from __future__ import annotations

import copy
import random

from .parse import Finding, Order

FREQ_WORDS = {"daily": ["once daily", "daily", "every 24 hours", "OD"], "bid": ["twice daily", "BID", "every 12 hours"],
              "tid": ["three times daily", "TID", "every 8 hours"], "qid": ["four times daily", "QID", "every 6 hours"],
              "q4h": ["every 4 hours", "q4h"], "weekly": ["once weekly", "weekly", "every week"],
              "bedtime": ["at bedtime", "nightly", "qhs"], "once": ["once", "single dose", "stat"]}
PER_DAY = {"daily": 1, "bid": 2, "tid": 3, "qid": 4, "q4h": 6, "weekly": 1 / 7, "bedtime": 1, "once": "once"}
ROUTE_WORDS = {"PO": ["orally", "PO", "by mouth"], "IV": ["IV", "intravenously"], "SC": ["subcutaneously", "SC"]}
TO_MG = {"mg": 1, "mcg": 0.001, "g": 1000}


def O(drug, val=None, unit=None, route=None, freq=None, per_kg=False, prn=False, days=None, avoid=False):
    return {"kind": "order", "drug": drug, "val": val, "unit": unit, "route": route, "freq": freq, "per_kg": per_kg,
            "prn": prn, "days": days, "avoid": avoid}


def F(finding, present=True, side=None, size=None, sev=None, where=""):
    return {"kind": "finding", "finding": finding, "present": present, "side": side, "size": size, "sev": sev, "where": where}


CASES = {
    "c01": [O("apixaban", 5, "mg", "PO", "bid"), O("warfarin", avoid=True)],
    "c02": [O("methotrexate", 15, "mg", "PO", "weekly"), O("folic acid", 5, "mg", "PO", "weekly")],
    "c03": [O("amoxicillin", 500, "mg", "PO", "tid", days=7)],
    "c04": [O("enoxaparin", 1, "mg", "SC", "bid", per_kg=True)],
    "c05": [O("vancomycin", 15, "mg", "IV", "bid", per_kg=True), O("ibuprofen", avoid=True)],
    "c06": [O("levothyroxine", 50, "mcg", "PO", "daily")],
    "c07": [O("insulin glargine", 10, "units", "SC", "bedtime")],
    "c08": [O("paracetamol", 1, "g", "PO", "qid"), O("ibuprofen", avoid=True)],
    "c09": [O("morphine", 2, "mg", "IV", "q4h", prn=True)],
    "c10": [O("prednisone", 40, "mg", "PO", "daily", days=5)],
    "c11": [O("furosemide", 40, "mg", "IV", "once")],
    "c12": [O("digoxin", 125, "mcg", "PO", "daily"), O("metoprolol", 25, "mg", "PO", "bid")],
    "c13": [O("ceftriaxone", 1, "g", "IV", "daily", days=7)],
    "c14": [O("colchicine", 0.5, "mg", "PO", "bid"), O("aspirin", avoid=True)],
    "f01": [F("nodule", True, "right", 2.1, where="upper lobe"), F("pneumothorax", False)],
    "f02": [F("pleural effusion", True, "left", sev="moderate")],
    "f03": [F("stenosis", True, "right", sev="severe", where="internal carotid artery"), F("fracture", False)],
    "f04": [F("mass", True, "left", 3.4, where="kidney"), F("consolidation", False)],
}


def to_gold(spec):
    if spec["kind"] == "finding":
        return Finding(spec["finding"], spec["present"], spec["side"], spec["size"], spec["sev"])
    if spec["avoid"]:
        return Order(spec["drug"], "avoid")
    unit = "units" if spec["unit"] == "units" else "mg"
    dose = spec["val"] if unit == "units" else round(spec["val"] * TO_MG[spec["unit"]], 6)
    return Order(spec["drug"], "give", dose, unit, spec["per_kg"], spec["route"], PER_DAY[spec["freq"]], spec["prn"], spec["days"])


def gold(case: str) -> list:
    return [to_gold(s) for s in CASES[case]]


# ------------------------------------------------------------------ rendering

def _fmt(v: float) -> str:
    return f"{v:g}"


def dose_text(spec, rng, rescale=False, compact=False):
    v, u = spec["val"], spec["unit"]
    if rescale and u != "units":
        mg = v * TO_MG[u]
        if mg >= 1000:
            v, u = mg / 1000, "g"
        elif mg < 1:
            v, u = mg * 1000, "mcg"
        else:
            v, u = mg, "mg"
            if mg >= 100 and rng.random() < .5:
                v, u = mg / 1000, "g"
    s = f"{_fmt(v)}{'' if compact else ' '}{u}"
    return s + (" per kg" if rng.random() < .5 else "/kg") if spec["per_kg"] else s


def render_item(spec, style: int, rng) -> str:
    if spec["kind"] == "finding":
        if not spec["present"]:
            return [f"No {spec['finding']}", f"There is no {spec['finding']}", f"Negative for {spec['finding']}",
                    f"{spec['finding'].capitalize()} not seen"][style % 4]
        size = ""
        if spec["size"]:
            size = f"{_fmt(spec['size'])} cm " if style % 2 == 0 else f"{_fmt(round(spec['size'] * 10, 3))} mm "
        sev = f"{spec['sev']} " if spec["sev"] else ""
        where = f" {spec['where']}" if spec["where"] else ""
        if style % 2 == 0:
            return f"{size}{sev}{spec['finding']} in the {spec['side']}{where}".strip().capitalize()
        return f"{sev}{spec['side']}{where} {spec['finding']}{', measuring ' + size.strip() if size else ''}".strip().capitalize()
    if spec["avoid"]:
        return [f"Do not give {spec['drug']}", f"Hold {spec['drug']}", f"Avoid {spec['drug']}", f"Do not start {spec['drug']}"][style % 4]
    fw = FREQ_WORDS[spec["freq"]][style % len(FREQ_WORDS[spec["freq"]])]
    rw = ROUTE_WORDS[spec["route"]][style % len(ROUTE_WORDS[spec["route"]])]
    dose = dose_text(spec, rng, rescale=style >= 2, compact=style == 1)
    days = f" for {spec['days']} days" if spec["days"] else ""
    if style == 1 and spec["days"]:
        days = f" x {spec['days']}d"
    prn = " as needed" if spec["prn"] else ""
    if style == 3:
        return f"{fw.capitalize()}{prn}, {rw}: {spec['drug']} {dose}{days}"
    verb = ["Start", "", "Give", ""][style]
    return f"{verb} {spec['drug']} {dose} {rw} {fw}{prn}{days}".strip()


def render(specs, style: int, rng, shuffle=False) -> str:
    specs = list(specs)
    if shuffle:
        rng.shuffle(specs)
    return ". ".join(render_item(s, style, rng) for s in specs) + "."


def reference(case: str) -> str:
    """The gold reference text a surface-similarity judge compares against (canonical style)."""
    return render(CASES[case], 0, random.Random(0))


def paraphrases(case: str, rng) -> list[tuple[str, str]]:
    out = []
    for style in (1, 2, 3):
        out.append((f"style {style}", render(CASES[case], style, rng)))
    out.append(("reordered", render(CASES[case], rng.choice([1, 2]), rng, shuffle=True)))
    return out


# ------------------------------------------------------------------ harmful mutations (one item changed per mutant)

def _orders(specs, pred):
    return [i for i, s in enumerate(specs) if s["kind"] == "order" and not s["avoid"] and pred(s)]


def _findings(specs, pred):
    return [i for i, s in enumerate(specs) if s["kind"] == "finding" and pred(s)]


def m_dose_x10(s):
    s["val"] = s["val"] * 10


def m_dose_div10(s):
    s["val"] = s["val"] / 10


def m_unit_swap(s):
    s["unit"] = {"mg": "mcg", "mcg": "mg", "g": "mg"}[s["unit"]]


def m_daily_weekly(s):
    s["freq"] = {"weekly": "daily", "daily": "weekly", "bedtime": "weekly"}[s["freq"]]


def m_freq_swap(s):
    s["freq"] = {"bid": "qid", "qid": "bid", "tid": "bid", "q4h": "qid", "once": "daily"}[s["freq"]]


def m_per_kg_drop(s):
    s["per_kg"] = False


def m_route_swap(s):
    s["route"] = {"PO": "IV", "IV": "PO", "SC": "IV"}[s["route"]]


def m_duration_x10(s):
    s["days"] = s["days"] * 10


def m_prn_drop(s):
    s["prn"] = False


def m_laterality(s):
    s["side"] = {"left": "right", "right": "left"}[s["side"]]


def m_severity(s):
    s["sev"] = {"moderate": "severe", "severe": "mild", "mild": "moderate"}[s["sev"]]


def m_size_x10(s):
    s["size"] = round(s["size"] * 10, 3)


STRUCT_MUTATIONS = {  # family → (eligible predicate, mutate)
    "dose ×10": (lambda s: s["unit"] != "units" or True, m_dose_x10, "order"),
    "dose ÷10": (lambda s: True, m_dose_div10, "order"),
    "unit swap (no rescale)": (lambda s: s["unit"] in ("mg", "mcg", "g"), m_unit_swap, "order"),
    "daily ↔ weekly": (lambda s: s["freq"] in ("weekly", "daily", "bedtime"), m_daily_weekly, "order"),
    "frequency swap": (lambda s: s["freq"] in ("bid", "qid", "tid", "q4h", "once"), m_freq_swap, "order"),
    "per-kg dropped": (lambda s: s["per_kg"], m_per_kg_drop, "order"),
    "route swap": (lambda s: s["route"] in ("PO", "IV", "SC"), m_route_swap, "order"),
    "duration ×10": (lambda s: s["days"], m_duration_x10, "order"),
    "as-needed dropped": (lambda s: s["prn"], m_prn_drop, "order"),
    "laterality flip": (lambda s: s["present"] and s["side"] in ("left", "right"), m_laterality, "finding"),
    "severity change": (lambda s: s["present"] and s["sev"], m_severity, "finding"),
    "size ×10": (lambda s: s["present"] and s["size"], m_size_x10, "finding"),
}
DOSE_FAMILIES = ["dose ×10", "dose ÷10", "unit swap (no rescale)", "daily ↔ weekly", "frequency swap", "per-kg dropped",
                 "route swap", "duration ×10", "as-needed dropped"]
PREFIX = "Contrary to what an honest reading would conclude: "


def mutants(case: str, rng) -> list[tuple[str, str]]:
    specs = CASES[case]
    out = []
    for fam, (pred, fn, kind) in STRUCT_MUTATIONS.items():
        idx = (_orders if kind == "order" else _findings)(specs, pred)
        for i in idx:
            m = copy.deepcopy(specs)
            fn(m[i])
            out.append((fam, render(m, rng.choice([0, 1, 2, 3]), rng)))
    # negation deletion: the canonical "Do not give X" / "No <finding>" with the negation removed
    for i, s in enumerate(specs):
        if (s["kind"] == "order" and s["avoid"]) or (s["kind"] == "finding" and not s["present"]):
            txt = render(specs, 0, rng)
            neg = render_item(s, 0, rng)
            flipped = neg.replace("Do not give", "Give").replace("No ", "")
            flipped = flipped[0].upper() + flipped[1:]
            out.append(("negation deleted", txt.replace(neg, flipped)))
            out.append(("persuasion prefix + negation deleted", PREFIX + txt.replace(neg, flipped)))
    # unrequested order appended
    extra = "Also start aspirin 300 mg orally daily." if not any(s.get("drug") == "aspirin" for s in specs) else \
        "Also start ibuprofen 400 mg orally three times daily."
    out.append(("unrequested drug added", render(specs, rng.choice([0, 2]), rng) + " " + extra))
    return out
