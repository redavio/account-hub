"""Hand-check three accounts at SQL -> Opportunity from the raw tables, without the engine's code.

  python3 seed/generate.py out && python3 -m accounthub run --folder out --out out/results.json
  python3 scripts/hand_check.py out
"""
import csv
import datetime as dt
import json
import sys

folder = sys.argv[1] if len(sys.argv) > 1 else "out"
D = lambda s: dt.date.fromisoformat(s) if s else None
acc = {a["account_id"]: a for a in csv.DictReader(open(f"{folder}/accounts.csv"))}
con = {c["contact_id"]: c for c in csv.DictReader(open(f"{folder}/contacts.csv"))}
deals = list(csv.DictReader(open(f"{folder}/deals.csv")))
tch = list(csv.DictReader(open(f"{folder}/touches.csv")))
r = json.load(open(f"{folder}/results.json"))
step = next(s for s in r["steps"] if s["from"] == "sql")
W = step["window_days"]
picks = ([x for x in step["accounts"] if x["advanced"] and x["coverage"] == "2+ roles"][:1]
         + [x for x in step["accounts"] if not x["advanced"] and x["depth"] == "Engaged"][:1]
         + [x for x in step["accounts"] if x["depth"] == "Not reached"][:1])
ok = True
for p in picks:
    a = acc[p["account_id"]]
    start = D(a["sql_date"])
    later = [D(d["created_date"]) for d in deals if d["account_id"] == a["account_id"]]
    later += [D(d["close_date"]) for d in deals if d["account_id"] == a["account_id"] and d["status"] == "won"]
    nxt = min(later, default=None)
    adv = nxt is not None and nxt <= start + dt.timedelta(days=W)
    end = nxt if adv else start + dt.timedelta(days=W + 1)
    mine = [t for t in tch if t["account_id"] == a["account_id"] and start <= D(t["date"]) < end]
    eng = [t for t in mine if t["kind"] == "engaged"]
    roles = sorted({con[t["contact_id"]]["role"] for t in eng})
    key = ["Champion", "Exec"]
    cov = [k for k in key if k in roles]
    hand = {"advanced": adv, "depth": "Engaged" if eng else ("Reached" if mine else "Not reached"),
            "coverage": "None" if not cov else ("1 role" if len(cov) == 1 else "2+ roles"),
            "roles_engaged": roles, "missing": [k for k in key if k not in roles]}
    engine = {"advanced": p["advanced"], "depth": p["depth"], "coverage": p["coverage"],
              "roles_engaged": p["roles_engaged"], "missing": p["missing_roles"]}
    same = hand == engine
    ok &= same
    print(f"{a['name']}: {'match' if same else 'MISMATCH'}  {hand}")
sys.exit(0 if ok else 1)
