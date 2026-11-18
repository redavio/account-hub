"""Generate fictional ABM data with planted truths, in the template's four-table shape.

Every company, person and number here is made up. The planted truths are effects the
generator builds in on purpose, so the analysis can be checked against a known answer:

  Real effects (the Caused by marketing view must find these):
    1. Paid social ad clicks raise Non-hand-raiser lead -> Hand-raiser.
    2. Event attendance raises SQL -> Opportunity.
    3. An engaged Finance contact raises Opportunity -> Closed won.
  No effect (the view must NOT report these):
    4. Web visits, at every step.
    5. Marketing emails that were sent but not engaged with ("Reached" only).

Run:  python3 seed/generate.py out/   (writes accounts.csv, contacts.csv, deals.csv, touches.csv)
"""
import csv
import os
import random
import sys
from datetime import date, timedelta

AS_OF = date(2026, 11, 15)
HISTORY_DAYS = 180              # six months of touches
N_ACCOUNTS = 1000
N_HOLDOUT = 100                 # target accounts set aside, no ABM touches
SEED = 41510

SEGMENTS = [("SMB", 0.4, 15000), ("Mid-market", 0.4, 45000), ("Enterprise", 0.2, 120000)]
ROLES = ["Exec", "Champion", "Finance", "IT", "Security", "Procurement"]
FIRST = ["Ava", "Ben", "Cara", "Dev", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jade", "Kai", "Lena",
         "Milo", "Nia", "Omar", "Pia", "Quinn", "Rosa", "Sam", "Tara", "Uma", "Vic", "Wren", "Yara"]
LAST = ["Abbott", "Brook", "Cole", "Dunn", "Ellis", "Frost", "Gray", "Hale", "Irwin", "Judd",
        "Kerr", "Lowe", "Marsh", "Nash", "Orr", "Pike", "Reed", "Shaw", "Tate", "Vale", "Wade", "York"]
WORD1 = ["North", "Blue", "Iron", "Bright", "Clear", "Quiet", "Swift", "Stone", "Silver", "Open",
         "Pine", "True", "Red", "Wide", "Calm", "Gold", "High", "Deep", "Far", "Prime"]
WORD2 = ["Ledger", "Harbor", "Forge", "Signal", "Field", "Works", "Labs", "Grid", "Path", "Loop",
         "Bridge", "Point", "Peak", "Yard", "Cloud", "Logic", "Metric", "Stack", "Wave", "Line"]
SOURCES = ["paid search", "paid social", "organic search (SEO)", "LLM answers (AEO)",
           "events and webinars", "referral and partner", "review sites", "direct", "sales outreach"]

# Stage order. Dates per account are "first date the account reached that stage".
STAGES = ["nhr_lead", "hand_raiser", "sql", "opportunity", "closed_won"]
# Mean days to advance, per step (the window the engine learns should come out near these).
DAYS_TO_ADVANCE = {"nhr_lead": 20, "hand_raiser": 12, "sql": 18, "opportunity": 40}


def pick_segment(rng):
    r, acc = rng.random(), 0
    for name, share, amount in SEGMENTS:
        acc += share
        if r < acc:
            return name, amount
    return SEGMENTS[-1][0], SEGMENTS[-1][2]


def generate(seed=SEED):
    rng = random.Random(seed)
    start = AS_OF - timedelta(days=HISTORY_DAYS)
    accounts, contacts, deals, touches = [], [], [], []
    names = set()
    holdout_ids = set(rng.sample(range(N_ACCOUNTS), N_HOLDOUT))
    tid = 0

    def touch(acct, contact, day, channel, kind, detail):
        nonlocal tid
        if day < start or day > AS_OF:
            return
        tid += 1
        touches.append({"touch_id": f"T{tid}", "account_id": acct, "contact_id": contact,
                        "date": day.isoformat(), "channel": channel, "kind": kind, "detail": detail})

    for i in range(N_ACCOUNTS):
        aid = f"A{i + 1:03d}"
        while True:   # 20 x 20 x 3 = 1,200 possible names
            name = f"{rng.choice(WORD1)}{rng.choice(WORD2)}{rng.choice(['', ' Inc', ' Co'])}"
            if name not in names:
                names.add(name)
                break
        segment, base_amount = pick_segment(rng)
        holdout = i in holdout_ids
        abm = not holdout

        # Buying committee: one Champion and one Exec always, the rest by chance.
        people = []
        for role in ROLES:
            n = 1 if role in ("Exec", "Champion") else (1 if rng.random() < 0.7 else 0)
            for _ in range(n):
                cid = f"C{len(contacts) + 1:04d}"
                contacts.append({"contact_id": cid, "account_id": aid,
                                 "name": f"{rng.choice(FIRST)} {rng.choice(LAST)}", "role": role})
                people.append((cid, role))
        by_role = {}
        for cid, role in people:
            by_role.setdefault(role, []).append(cid)

        def someone(role=None):
            if role:
                return rng.choice(by_role[role]) if role in by_role else None
            return rng.choice(people)[0]

        # Where the account enters, and when. Entering lower in the funnel keeps every step
        # populated within six months of history.
        entry = rng.choices(STAGES[:4], weights=[50, 20, 15, 15])[0]
        day = start + timedelta(days=rng.randint(0, HISTORY_DAYS - 20))
        dates = {s: "" for s in STAGES}
        dates[entry] = day.isoformat()
        stage = entry
        amount = round(base_amount * rng.uniform(0.6, 1.5), -2)

        while stage != "closed_won":
            nxt = STAGES[STAGES.index(stage) + 1]
            dur = max(2, int(rng.expovariate(1 / DAYS_TO_ADVANCE[stage])))
            span_end = day + timedelta(days=dur)

            def when():
                return day + timedelta(days=rng.randint(0, max(0, dur - 1)))

            # Touches during this stage. Web visits and sent-only emails are noise everywhere.
            for _ in range(rng.choice([0, 0, 1, 2, 3])):
                touch(aid, someone(), when(), "website", "engaged", "web visit")
            if abm:
                for _ in range(rng.choice([0, 1, 2])):
                    touch(aid, someone(), when(), "email", "reached", "marketing email sent")

            effect = 0.0
            if stage == "nhr_lead":
                clicked = abm and rng.random() < 0.45
                if clicked:
                    touch(aid, someone(), when(), "paid social", "engaged", "ad click")
                elif abm and rng.random() < 0.5:
                    touch(aid, someone(), when(), "paid social", "reached", "ad impression")
                p = 0.20 + (0.30 if clicked else 0.0)
            elif stage == "hand_raiser":
                if rng.random() < 0.6:
                    touch(aid, someone("Champion"), when(), "sales outreach", "engaged", "meeting")
                p = 0.55
            elif stage == "sql":
                attended = abm and rng.random() < 0.45
                if attended:
                    touch(aid, someone(), when(), "events and webinars", "engaged", "event attendance")
                if rng.random() < 0.6:
                    touch(aid, someone("Exec"), when(), "sales outreach", "engaged", "meeting")
                p = 0.25 + (0.35 if attended else 0.0)
            else:  # opportunity
                fin = someone("Finance")
                finance_engaged = fin is not None and rng.random() < 0.5
                if finance_engaged:
                    touch(aid, fin, when(), "sales outreach", "engaged", "meeting")
                if rng.random() < 0.7:
                    touch(aid, someone("Exec"), when(), "sales outreach", "engaged", "email reply")
                p = 0.15 + (0.40 if finance_engaged else 0.0)

            if rng.random() >= p or span_end > AS_OF:
                break
            # A few non-hand-raiser leads skip straight to SQL (rare).
            if stage == "nhr_lead" and rng.random() < 0.08:
                nxt = "sql"
            day = span_end
            dates[nxt] = day.isoformat()
            stage = nxt

        if dates["opportunity"]:
            won = bool(dates["closed_won"])
            deals.append({"deal_id": f"D{len(deals) + 1:03d}", "account_id": aid, "amount": amount,
                          "created_date": dates["opportunity"],
                          "status": "won" if won else ("open" if rng.random() < 0.6 else "lost"),
                          "close_date": dates["closed_won"] if won else ""})

        source = rng.choice(SOURCES)
        accounts.append({"account_id": aid, "name": name, "segment": segment, "target": "yes",
                         "holdout": "yes" if holdout else "no", "original_source": source,
                         "nhr_lead_date": dates["nhr_lead"], "hand_raiser_date": dates["hand_raiser"],
                         "sql_date": dates["sql"]})
    return {"accounts": accounts, "contacts": contacts, "deals": deals, "touches": touches}


def write(tables, out):
    os.makedirs(out, exist_ok=True)
    for name, rows in tables.items():
        with open(os.path.join(out, f"{name}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    t = generate()
    write(t, sys.argv[1] if len(sys.argv) > 1 else "out")
    print({k: len(v) for k, v in t.items()})
