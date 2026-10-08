"""Dose-mutation benchmark: hack rate / false-reject rate per grader, held-out check, and best-of-N under optimisation pressure.

    python demo.py      # console summary + out/report.html
"""
from __future__ import annotations

import html
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from doseverify.bench import CASES, DOSE_FAMILIES, gold, mutants, paraphrases, reference
from doseverify.verify import token_f1, verify

HERE = Path(__file__).parent
OUT = HERE / "out"
SEED = 7


def build_dev():
    rng = random.Random(SEED)
    para, muts = [], []
    for c in CASES:
        para += [(c, name, t) for name, t in paraphrases(c, rng)]
        muts += [(c, fam, t) for fam, t in mutants(c, rng)]
    return para, muts


def graders(para):
    """Surface-similarity baselines get the threshold that accepts 95 % of true paraphrases (fair calibration)."""
    def calibrate(fn):
        s = sorted(fn(t, reference(c)) for c, _, t in para)
        return s[int(len(s) * 0.05)]
    lex = lambda t, c: token_f1(t, reference(c))
    blind = lambda t, c: token_f1(t, reference(c), numbers=False)
    th_lex, th_blind = calibrate(lambda t, r: token_f1(t, r)), calibrate(lambda t, r: token_f1(t, r, numbers=False))
    return {
        "Lexical judge (token F1)": (lambda t, c: lex(t, c) >= th_lex, lex),
        "Number-blind judge": (lambda t, c: blind(t, c) >= th_blind, blind),
        "Structured verifier": (lambda t, c: verify(t, gold(c)).status == "PASS",
                                lambda t, c: (lambda v: (v.status == "PASS") + v.reward)(verify(t, gold(c)))),
    }, {"lex": th_lex, "blind": th_blind}


def best_of_n(para, muts, gs, n=16, seeds=60):
    pool = defaultdict(list)
    for c, _, t in para:
        pool[c].append((t, False))
    for c, _, t in muts:
        pool[c].append((t, True))
    out = {}
    for name, (_, score) in gs.items():
        harmful = total = 0
        for s in range(seeds):
            rng = random.Random(1000 + s)
            for c, cands in pool.items():
                pick = rng.sample(cands, min(n, len(cands)))
                rng.shuffle(pick)
                best = max(pick, key=lambda x: score(x[0], c))
                harmful += best[1]
                total += 1
        out[name] = (harmful, total)
    return out


def bar(v, color):
    return f"<div class=b><div style='width:{v * 100:.1f}%;background:{color}'></div><span>{v:.0%}</span></div>"


def main() -> int:
    t0 = time.perf_counter()
    para, muts = build_dev()
    gs, th = graders(para)
    fams = list(dict.fromkeys(f for _, f, _ in muts))

    print(f"\n== dev set: {len(CASES)} gold cases · {len(para)} true paraphrases · {len(muts)} harmful mutants ({len(fams)} families)")
    print(f"   baselines calibrated to accept 95% of true paraphrases (thresholds: lexical {th['lex']:.2f}, number-blind {th['blind']:.2f})\n")
    table = {}
    for name, (accept, _) in gs.items():
        fr = sum(not accept(t, c) for c, _, t in para) / len(para)
        per = {f: [accept(t, c) for c, ff, t in muts if ff == f] for f in fams}
        hack = sum(sum(v) for v in per.values()) / len(muts)
        dose = [x for f in DOSE_FAMILIES if f in per for x in per[f]]
        table[name] = (fr, hack, sum(dose) / len(dose), {f: sum(v) / len(v) for f, v in per.items()})
        print(f"  {name:<26} false-reject {fr:5.1%}   hack rate {hack:5.1%}   dose-family hack rate {sum(dose) / len(dose):5.1%}")
    print("\n  hack rate by family:            " + "  ".join(f"{n.split()[0][:8]:>8}" for n in gs))
    for f in fams:
        print(f"  {f:<32}" + "  ".join(f"{table[n][3][f]:>8.0%}" for n in gs))

    held = json.loads((HERE / "data" / "heldout.json").read_text(encoding="utf-8"))["items"]
    hc = Counter((it["label"], verify(it["text"], gold(it["case"])).status) for it in held)
    print(f"\n== held-out (hand-written after the parser was frozen, {len(held)} items):")
    print(f"  harmful: PASS {hc[('harmful', 'PASS')]} · FAIL {hc[('harmful', 'FAIL')]} · ABSTAIN {hc[('harmful', 'ABSTAIN')]}")
    print(f"  true paraphrases: PASS {hc[('ok', 'PASS')]} · ABSTAIN {hc[('ok', 'ABSTAIN')]} (→ LLM judge / human) · wrong FAIL {hc[('ok', 'FAIL')]}")

    bon = best_of_n(para, muts, gs)
    print("\n== best-of-16 selection (60 seeds × 18 cases): how often the top-scored answer is a harmful mutant")
    for name, (h, tot) in bon.items():
        print(f"  {name:<26} {h / tot:6.1%}  ({h}/{tot})")

    ex_c = "c02"
    want = ["daily ↔ weekly", "dose ×10", "unit swap (no rescale)", "unrequested drug added"]
    first = {}
    for c, f, t in muts:
        if c == ex_c and f in want and f not in first:
            first[f] = t
    ex = [(f, first[f], verify(first[f], gold(ex_c))) for f in want if f in first]
    OUT.mkdir(exist_ok=True)
    colors = {"Lexical judge (token F1)": "#c9822b", "Number-blind judge": "#b3261e", "Structured verifier": "#1f7a4d"}
    fam_rows = "".join(f"<tr><td>{html.escape(f)}</td>" + "".join(f"<td>{bar(table[n][3][f], colors[n])}</td>" for n in gs) + "</tr>" for f in fams)
    summ = "".join(f"<tr><td><b>{html.escape(n)}</b></td><td>{table[n][0]:.1%}</td><td>{table[n][1]:.1%}</td><td>{table[n][2]:.1%}</td>"
                   f"<td>{bon[n][0] / bon[n][1]:.1%}</td></tr>" for n in gs)
    exs = "".join(f"<tr><td>{html.escape(f)}</td><td class=mono>{html.escape(t)}</td><td><b>{v.status}</b> {html.escape('; '.join(v.contradicted + v.unsupported))}</td></tr>"
                  for f, t, v in ex)
    (OUT / "report.html").write_text(f"""<!doctype html><meta charset=utf-8><title>Dose-mutation benchmark</title>
<style>body{{font:14px/1.45 'Segoe UI',system-ui,sans-serif;margin:30px;max-width:1400px;color:#1d1d1f;background:#fafaf8}}
h1{{font-size:23px;margin:0}}h2{{font-size:17px;margin:24px 0 8px}}.sub{{color:#666}}table{{border-collapse:collapse;width:100%;background:#fff}}
td,th{{border-top:1px solid #e5e5e0;padding:6px 10px;text-align:left;vertical-align:top}}.mono{{font-family:Consolas,monospace;font-size:12px}}
.b{{position:relative;background:#f0efe9;height:18px;border-radius:4px;width:240px}}.b div{{height:18px;border-radius:4px}}
.b span{{position:absolute;left:6px;top:0;font-size:12px;color:#111}}</style>
<h1>Dose-mutation benchmark for medical RL reward functions</h1>
<div class=sub>{len(CASES)} synthetic gold cases (medication orders + imaging findings) · {len(para)} true paraphrases · {len(muts)} harmful mutants in {len(fams)} families ·
baselines calibrated to accept 95% of true paraphrases · gold doses are synthetic test targets, not clinical guidance</div>
<h2>Summary</h2><table><tr><th>grader</th><th>false-reject (true paraphrases)</th><th>hack rate (all mutants)</th><th>hack rate (dose families)</th><th>best-of-16 picks harmful</th></tr>{summ}</table>
<h2>Hack rate by mutation family (lower is better)</h2><table><tr><th>family</th>{''.join(f'<th>{html.escape(n)}</th>' for n in gs)}</tr>{fam_rows}</table>
<h2>Held-out set (hand-written after the parser was frozen)</h2>
<p>Harmful: <b>{hc[('harmful', 'PASS')]} passed</b>, {hc[('harmful', 'FAIL')]} failed, {hc[('harmful', 'ABSTAIN')]} abstained.
True paraphrases: {hc[('ok', 'PASS')]} passed, <b>{hc[('ok', 'ABSTAIN')]} abstained</b> (unreadable field → defer to an LLM judge / human), <b>{hc[('ok', 'FAIL')]} wrongly failed</b>.</p>
<h2>Example verdicts ({ex_c}: methotrexate 15 mg weekly + folic acid)</h2><table>{exs}</table>
<p class=sub>Unofficial prototype by Kushagra Pratap Singh. Not affiliated with BioStack Platforms.</p>""", encoding="utf-8")
    print(f"\nreport: out/report.html  ({time.perf_counter() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
