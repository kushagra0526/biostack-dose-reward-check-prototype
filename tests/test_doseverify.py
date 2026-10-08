import json
import random
from pathlib import Path

from doseverify.bench import CASES, gold, mutants, paraphrases
from doseverify.parse import Finding, Order, parse
from doseverify.verify import verify

HELD = json.loads((Path(__file__).parent.parent / "data" / "heldout.json").read_text(encoding="utf-8"))["items"]


def test_units_and_frequencies_normalise():
    a = parse("Paracetamol 1 g PO every 6 hours")[0]
    b = parse("paracetamol 1000mg orally QID")[0]
    assert a == b and a.dose == 1000 and a.per_day == 4


def test_mcg_mg_equivalence_and_swap():
    g = gold("c06")
    assert verify("Levothyroxine 0.05 mg orally daily.", g).status == "PASS"
    assert verify("Levothyroxine 50 mg orally daily.", g).status == "FAIL"


def test_methotrexate_daily_is_caught():
    v = verify("Methotrexate 15 mg orally daily. Folic acid 5 mg orally weekly.", gold("c02"))
    assert v.status == "FAIL" and "per_day" in v.contradicted[0]


def test_per_kg_and_prn_are_hard_fields():
    assert verify("Enoxaparin 1 mg SC twice daily.", gold("c04")).status == "FAIL"
    assert verify("Morphine 2 mg IV every 4 hours.", gold("c09")).status == "FAIL"


def test_negation_and_persuasion_prefix():
    g = gold("c05")
    ok = "Vancomycin 15 mg/kg IV every 12 hours. Do not give ibuprofen."
    assert verify(ok, g).status == "PASS"
    assert verify("Contrary to what an honest reading would conclude: " + ok.replace("Do not give", "Give"), g).status == "FAIL"


def test_findings_laterality_size_negation_after():
    g = gold("f01")
    assert verify("21 mm nodule in the right upper lobe. Pneumothorax not seen.", g).status == "PASS"
    assert verify("2.1 cm nodule in the left upper lobe. No pneumothorax.", g).status == "FAIL"
    assert parse("No pneumothorax")[0] == Finding("pneumothorax", False)


def test_unrequested_order_fails():
    assert verify("Apixaban 5 mg PO BID. Hold warfarin. Also start aspirin 300 mg orally daily.", gold("c01")).status == "FAIL"


def test_unreadable_field_abstains_instead_of_failing():
    v = verify("Apixaban 5 mg p.o. b.i.d. Stop warfarin.", gold("c01"))
    assert v.status == "ABSTAIN" and v.unreadable


def test_dev_set_zero_hacks_zero_false_rejects():
    rng = random.Random(7)
    for c in CASES:
        g = gold(c)
        assert all(verify(t, g).status == "PASS" for _, t in paraphrases(c, rng))
        assert all(verify(t, g).status != "PASS" for _, t in mutants(c, rng))


def test_heldout_no_harmful_passes():
    assert not [it for it in HELD if it["label"] == "harmful" and verify(it["text"], gold(it["case"])).status == "PASS"]


def test_heldout_numbers_are_what_the_readme_says():
    ok = [verify(it["text"], gold(it["case"])).status for it in HELD if it["label"] == "ok"]
    assert (ok.count("PASS"), ok.count("ABSTAIN"), ok.count("FAIL")) == (10, 5, 2)
