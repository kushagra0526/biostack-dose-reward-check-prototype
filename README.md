# Dose-mutation benchmark + structured reward verifier for medical RL (prototype)

**The problem.** BioStack's post [The Grader Is the Attack Surface in Medical AI](https://www.getbiostack.com/blog/trojan-horsing-evals) shows that LLM judges used as RL rewards approve corrupted medical answers. For example, a single deleted "not" slips past most models. The post lists **"dose-specific numeric mutations aren't yet evaluated"** as an open problem. Their [imaging environment write-up](https://www.getbiostack.com/blog/only-17-of-700-ai-attempts-found-every-required-finding) names "losing qualifiers (laterality, severity)" as a failure mode, and their [launch](https://www.ycombinator.com/launches/QUp-biostack-platforms-realistic-healthcare-simulation-environments) includes medication-adjustment tasks. A dose error is the most dangerous thing a hackable reward can quietly train into a model.

**What I built.**
1. **A dose-mutation benchmark.** 15 labelled harmful mutation families, applied one item at a time to synthetic gold answers:
   - dose ×10 / ÷10
   - mg↔mcg↔g swapped *without* rescaling
   - daily↔weekly (the classic methotrexate error), BID↔QID
   - per-kg dropped, route swap, duration ×10, "as needed" dropped
   - an unrequested drug added
   - negation deleted, with and without a persuasion prefix
   - laterality flip, severity change, size ×10

   It also has **true paraphrases that must still pass**: 1 g = 1000 mg, 0.05 mg = 50 mcg, BID = twice daily = every 12 hours, PO = orally, abbreviations, and reordering.
2. **A structured verifier usable as a reward component.** It parses free-text orders and findings into structured fields: drug, dose in base units, per-kg, route, doses per day, as-needed, duration, avoid/hold, and for findings: side, size, severity, present/absent. Each field is compared to the gold. It returns **PASS / FAIL / ABSTAIN** plus a reward of (matched − contradicted − unsupported) / required. **ABSTAIN** means "I couldn't read a required field", and the case should go to an LLM judge or a human. It is not treated as a fail.
3. **Best-of-N under optimisation pressure.** For each case, sample 16 candidates (true paraphrases + mutants), let each grader pick its favourite, and count how often the pick is harmful. This is a cheap stand-in for what RL does to a reward.

## Results

| grader | false-reject on true paraphrases | hack rate (all 125 mutants) | hack rate (dose families) | best-of-16 picks harmful |
|---|---|---|---|---|
| Lexical judge (token F1) | 2.8% | 91.2% | 87.1% | 75.1% |
| Number-blind judge | 2.8% | 93.6% | 90.6% | 89.4% |
| **Structured verifier** | **0.0%** | **0.0%** | **0.0%** | **0.0%** |

The baselines are calibrated to accept 95% of true paraphrases, so they get a fair threshold.

**Held-out set (34 items, hand-written *after* the parser was frozen, not tuned on):**
- **Harmful:** **0 of 17 passed** (15 FAIL, 2 ABSTAIN).
- **True paraphrases:** 10 PASS, **5 ABSTAIN** (it couldn't read things like "milligrams", "p.o. b.i.d.", "every morning"), and **2 wrongly FAILED**.
  - "warfarin to be held" has its negation *after* the drug name.
  - "digoxin … daily and metoprolol … BID" puts two drugs in one sentence.

The honest takeaway: a deterministic layer is cheap and fails closed on dose errors, but it must be allowed to abstain. Unknown phrasing should go to an LLM judge, not be scored zero. Otherwise RL would push models toward one canonical phrasing.

![report](docs/report.png)

## Honest limits
- I wrote the gold cases, the mutation operators and the held-out set myself. The dev-set 0% shows the verifier handles the families it was designed for. The held-out set is the better signal, and it's small (34).
- The baselines are simple surface-similarity judges, not LLM judges. I didn't run LLM judges here; BioStack's post already measured those.
- Gold doses are synthetic test targets, not clinical guidance. No patient data is used.

## Run

```bash
python demo.py              # benchmark, held-out, best-of-N → out/report.html
pip install pytest && python -m pytest -q   # 11 tests
```

Standard-library Python only. It runs in about 3 s.

## Layout

```
doseverify/parse.py    free text → Order / Finding (unit, frequency, route, duration, negation normalisation)
doseverify/verify.py   PASS / FAIL / ABSTAIN + reward; surface-similarity baselines
doseverify/bench.py    gold cases, paraphrase renderer, 15 mutation families
data/heldout.json      34 hand-written held-out items
```

Unofficial prototype by Kushagra Pratap Singh. Not affiliated with BioStack Platforms.
