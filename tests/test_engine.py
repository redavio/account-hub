import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "seed"))

from accounthub import analyze  # noqa: E402
from accounthub.stats import exact_stratified, holm, sample_check  # noqa: E402
from generate import generate  # noqa: E402

TRUE = {("nhr_lead", "paid social", "engaged"), ("sql", "events and webinars", "engaged"),
        ("opportunity", "Finance", "engaged")}


def findings(result):
    out = set()
    for st in result["steps"]:
        for x in st["incremental"]["channels"] + st["incremental"]["roles"]:
            if x["status"] in ("lift", "negative"):
                out.add((st["from"], x.get("channel") or x.get("role"), x["exposure"], x["status"]))
    return out


class PlantedTruths(unittest.TestCase):
    def test_demo_data_finds_every_truth_and_nothing_false(self):
        found = findings(analyze(generate()))
        self.assertEqual({f[:3] for f in found if f[3] == "lift"}, TRUE)
        self.assertEqual([f for f in found if f[:3] not in TRUE], [])

    def test_recovery_across_datasets(self):
        missed = false_runs = 0
        for seed in range(1, 11):
            found = findings(analyze(generate(seed)))
            missed += len(TRUE - {f[:3] for f in found if f[3] == "lift"})
            false_runs += bool([f for f in found if f[:3] not in TRUE])
        self.assertLessEqual(missed, 6)       # finds at least 24 of 30 real effects
        self.assertLessEqual(false_runs, 2)   # a stray false finding in at most 2 runs of 10


class Stats(unittest.TestCase):
    def test_exact_test_matches_fisher(self):
        # One stratum, 8/10 vs 2/10: Fisher's exact two-sided p = 0.0230.
        r = exact_stratified([(10, 8, 10, 2)])
        self.assertAlmostEqual(r["p"], 0.0230, places=3)
        self.assertAlmostEqual(r["lift"], 0.6)

    def test_holm(self):
        self.assertEqual([round(x, 3) for x in holm([0.01, 0.04, 0.03])], [0.03, 0.06, 0.06])

    def test_sample_check(self):
        enough, more = sample_check(0.05, 0.3, 50, 50)
        self.assertFalse(enough)
        self.assertGreater(more, 1000)
        self.assertEqual(sample_check(0.4, 0.2, 200, 200), (True, 0))


def tiny(**acct):
    a = {"account_id": "A1", "name": "X", "segment": "SMB", "target": "yes", "holdout": "no",
         "original_source": "paid search", "nhr_lead_date": "", "hand_raiser_date": "", "sql_date": ""}
    a.update(acct)
    return a


class Rules(unittest.TestCase):
    def test_skip_counts_as_advance_and_window_from_history(self):
        accounts = [tiny(account_id=f"A{i}", nhr_lead_date="2026-01-01", sql_date=f"2026-01-{10 + i:02d}") for i in range(5)]
        accounts.append(tiny(account_id="B", nhr_lead_date="2026-01-01"))
        r = analyze({"accounts": accounts, "contacts": [], "deals": [],
                     "touches": [{"account_id": "A0", "contact_id": "", "date": "2025-12-01", "channel": "email", "kind": "reached"}]},
                    {"as_of": "2026-06-01"})
        step = r["steps"][0]
        self.assertEqual(step["window_source"], "history")
        self.assertEqual(step["window_days"], 12)          # 4 of 5 (80%) advanced within 12 days
        self.assertEqual((step["eligible"], step["advanced"]), (6, 4))  # skips to SQL count; day 13 is past the 12-day window

    def test_recent_accounts_wait_for_their_window(self):
        accounts = [tiny(account_id=f"A{i}", nhr_lead_date="2026-01-01", hand_raiser_date="2026-01-11") for i in range(5)]
        accounts.append(tiny(account_id="NEW", nhr_lead_date="2026-05-28"))
        r = analyze({"accounts": accounts, "contacts": [], "deals": [],
                     "touches": [{"account_id": "A0", "contact_id": "", "date": "2025-12-01", "channel": "email", "kind": "reached"}]},
                    {"as_of": "2026-06-01"})
        ids = {a["account_id"] for a in r["steps"][0]["accounts"]}
        self.assertNotIn("NEW", ids)

    def test_window_fallback_to_sales_cycle(self):
        accounts = [tiny(account_id="A", nhr_lead_date="2026-01-01")]
        r = analyze({"accounts": accounts, "contacts": [], "deals": [], "touches": []},
                    {"as_of": "2026-06-01", "sales_cycle_days": 45})
        self.assertEqual((r["steps"][0]["window_days"], r["steps"][0]["window_source"]), (45, "sales cycle setting"))

    def test_value_is_pipeline(self):
        accounts = [tiny(account_id="A", nhr_lead_date="2026-01-01", sql_date="2026-01-05"),
                    tiny(account_id="B", nhr_lead_date="2026-01-01", sql_date="2026-01-05")]
        deals = [{"deal_id": "D", "account_id": "A", "amount": "50000", "created_date": "2026-01-20", "status": "open", "close_date": ""}]
        r = analyze({"accounts": accounts, "contacts": [], "deals": deals, "touches": []},
                    {"as_of": "2026-06-01", "sales_cycle_days": 30})
        sql = next(f for f in r["funnel"] if f["stage"] == "sql")
        self.assertEqual(sql["value"], 25000)               # half of SQLs become a $50K Opp


if __name__ == "__main__":
    unittest.main()


class Review(unittest.TestCase):
    """Fixes from the fresh review."""

    def test_advance_after_the_window_does_not_count(self):
        accounts = [tiny(account_id=f"A{i}", nhr_lead_date="2026-01-01", hand_raiser_date="2026-01-11") for i in range(5)]
        accounts.append(tiny(account_id="LATE", nhr_lead_date="2026-01-01", hand_raiser_date="2026-04-01"))
        r = analyze({"accounts": accounts, "contacts": [], "deals": [],
                     "touches": [{"account_id": "A0", "contact_id": "", "date": "2025-12-01", "channel": "email", "kind": "reached"}]},
                    {"as_of": "2026-06-01"})
        late = next(a for a in r["steps"][0]["accounts"] if a["account_id"] == "LATE")
        self.assertFalse(late["advanced"])

    def test_gaps_skip_holdout_and_use_current_stage(self):
        r = analyze(generate())
        holdout = {a["account_id"] for a in r["accounts"] if a["holdout"]}
        self.assertFalse([g for g in r["gaps"] if g["account_id"] in holdout])
        stage = {a["account_id"]: a["stage"] for a in r["accounts"]}
        self.assertTrue(all(g["stage"] == stage[g["account_id"]] for g in r["gaps"]))

    def test_exact_test_is_exact_at_size(self):
        r = exact_stratified([(300, 90, 300, 60), (250, 50, 250, 40), (200, 70, 200, 50)])
        self.assertLess(r["p"], 0.01)
        self.assertGreater(r["lift"], 0)
