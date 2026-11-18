"""Account Hub engine: four tables in, one results file out.

Tables (same columns as the files in template/; HubSpot is read into the same shape):
  accounts: account_id, name, segment, target, holdout, original_source,
            nhr_lead_date, hand_raiser_date, sql_date
  contacts: contact_id, account_id, name, role
  deals:    deal_id, account_id, amount, created_date, status (open|won|lost), close_date
  touches:  touch_id, account_id, contact_id, date, channel, kind (engaged|reached), detail

Opportunity date = first deal created; Closed won date = first won deal's close date.

Rules, in one place:
  Window     each step's window = days within which 80% of past advancing accounts advanced
             (fallback: the sales cycle setting, else the whole time at the stage).
  Advanced   reached any later stage within the window. Touches count from the stage date,
             inside the window, and only before the advance.
  Cohorts    an account counts toward a step only once its window has passed; comparisons hold
             the cohort (month the account entered the stage) and segment fixed.
  Caused     every channel and role is tested at once (logistic regression with segment and
             cohort), so each is judged with the others held fixed; the holdout comparison is an
             exact stratified test (segment x cohort). One Holm correction covers every test.
"""
from datetime import date, timedelta
from math import ceil

from .stats import exact_stratified, holm, logit, predict, sample_check, wald_p

STAGES = ["nhr_lead", "hand_raiser", "sql", "opportunity", "closed_won"]
STAGE_LABELS = {"nhr_lead": "Non-hand-raiser lead", "hand_raiser": "Hand-raiser", "sql": "SQL",
                "opportunity": "Opportunity", "closed_won": "Closed won"}
DEPTHS = ["Not reached", "Reached", "Engaged"]
COVERAGE = ["None", "1 role", "2+ roles"]
YES = ("yes", "true", "1", "y")

DEFAULTS = {
    "as_of": None,                       # default: latest date in the data
    "key_roles": {                       # which roles matter at each step (from-stage -> roles)
        "nhr_lead": ["Champion"],
        "hand_raiser": ["Champion"],
        "sql": ["Champion", "Exec"],
        "opportunity": ["Exec", "Finance"],
    },
    "enterprise_extra_roles": {"opportunity": ["Security"]},
    "enterprise_segment": "Enterprise",
    "sales_cycle_days": None,            # window fallback when history is too thin
    "window_percentile": 0.8,
    "min_history_for_window": 5,         # advancing accounts needed to read a percentile at all
    "non_marketing_channels": ["sales outreach", "direct"],  # not credited to marketing
    "channel_costs": {},                 # channel -> cost over the period
    "alpha": 0.05,
    "power": 0.8,
    "max_more_multiple": 10,             # beyond 10x today's accounts, a lift is too small to act on
}


def _d(s):
    return date.fromisoformat(str(s)[:10]) if s else None


def _settings(user):
    s = {**DEFAULTS, **(user or {})}
    s["key_roles"] = {**DEFAULTS["key_roles"], **(user or {}).get("key_roles", {})}
    return s


def _prepare(tables):
    accounts = {}
    for a in tables["accounts"]:
        if str(a.get("target", "yes")).strip().lower() not in YES:
            continue
        accounts[a["account_id"]] = {
            "id": a["account_id"], "name": a.get("name") or a["account_id"],
            "segment": a.get("segment") or "All", "holdout": str(a.get("holdout", "")).strip().lower() in YES,
            "source": a.get("original_source") or "", "dates": {
                "nhr_lead": _d(a.get("nhr_lead_date")), "hand_raiser": _d(a.get("hand_raiser_date")),
                "sql": _d(a.get("sql_date")), "opportunity": None, "closed_won": None},
            "pipeline": 0.0, "won": 0.0}
    for dl in tables.get("deals", []):
        a = accounts.get(dl["account_id"])
        if not a:
            continue
        created, amount = _d(dl.get("created_date")), float(dl.get("amount") or 0)
        if created and (a["dates"]["opportunity"] is None or created < a["dates"]["opportunity"]):
            a["dates"]["opportunity"] = created
        a["pipeline"] += amount
        if dl.get("status") == "won" and dl.get("close_date"):
            closed = _d(dl["close_date"])
            if a["dates"]["closed_won"] is None or closed < a["dates"]["closed_won"]:
                a["dates"]["closed_won"] = closed
            a["won"] += amount
    roles = {c["contact_id"]: c.get("role") or "" for c in tables.get("contacts", [])}
    touches = {}
    for t in tables.get("touches", []):
        if t["account_id"] in accounts and t.get("date"):
            touches.setdefault(t["account_id"], []).append({
                "date": _d(t["date"]), "channel": (t.get("channel") or "other").strip(),
                "kind": "engaged" if str(t.get("kind", "")).strip().lower() == "engaged" else "reached",
                "role": roles.get(t.get("contact_id"), "")})
    return accounts, touches


def _later(a, stage):
    """First date the account reached any stage after `stage`."""
    i = STAGES.index(stage)
    ds = [a["dates"][s] for s in STAGES[i + 1:] if a["dates"][s]]
    return min(ds) if ds else None


def _current(a):
    """The latest stage the account has reached."""
    return next((st for st in reversed(STAGES) if a["dates"][st]), None)


def _percentile(xs, q):
    """Nearest rank: the smallest value with at least q of the list at or below it."""
    xs = sorted(xs)
    return xs[max(0, min(len(xs) - 1, ceil(q * len(xs)) - 1))]


def _key_roles(s, stage, segment):
    key = list(s["key_roles"].get(stage, []))
    if segment == s["enterprise_segment"]:
        key += [r for r in s["enterprise_extra_roles"].get(stage, []) if r not in key]
    return key


def analyze(tables, settings=None):
    s = _settings(settings)
    accounts, touches = _prepare(tables)
    all_dates = [t["date"] for ts in touches.values() for t in ts] + \
        [d for a in accounts.values() for d in a["dates"].values() if d]
    if not all_dates:
        raise ValueError("No dates found: give stage dates, deals or touches.")
    as_of = _d(s["as_of"]) if s["as_of"] else max(all_dates)
    history_start = min((t["date"] for ts in touches.values() for t in ts), default=as_of)
    non_mkt = set(s["non_marketing_channels"])

    opp_amounts = [a["pipeline"] for a in accounts.values() if a["dates"]["opportunity"]]
    avg_opp = sum(opp_amounts) / len(opp_amounts) if opp_amounts else 0.0
    won_amounts = [a["won"] for a in accounts.values() if a["dates"]["closed_won"]]
    avg_won = sum(won_amounts) / len(won_amounts) if won_amounts else 0.0

    windows, wsources = {}, {}
    for frm in STAGES[:-1]:
        durations = [(_later(a, frm) - a["dates"][frm]).days for a in accounts.values()
                     if a["dates"][frm] and _later(a, frm)]
        if len(durations) >= s["min_history_for_window"]:
            windows[frm], wsources[frm] = max(1, _percentile(durations, s["window_percentile"])), "history"
        elif s["sales_cycle_days"]:
            windows[frm], wsources[frm] = int(s["sales_cycle_days"]), "sales cycle setting"
        else:
            windows[frm], wsources[frm] = None, "whole time at the stage"

    steps = [_step(frm, STAGES[i + 1], windows[frm], wsources[frm], accounts, touches, s, as_of, history_start, non_mkt)
             for i, frm in enumerate(STAGES[:-1])]

    # Value of each stage in pipeline $: share that become an Opportunity x average Opportunity.
    # An account counts once it has had time to reach Opportunity (every window up to it has passed).
    value = {"opportunity": avg_opp, "closed_won": avg_won}
    for i, st in enumerate(STAGES[:3]):
        span = [windows[x] for x in STAGES[i:3]]
        wait = sum(span) if all(span) else None
        matured = [a for a in accounts.values() if a["dates"][st]
                   and (wait is None or a["dates"][st] + timedelta(days=wait) <= as_of)]
        value[st] = (sum(1 for a in matured if a["dates"]["opportunity"]) / len(matured) * avg_opp) if matured else 0.0

    headline = _headline(accounts, steps, non_mkt, s, windows, as_of, history_start)

    # One Holm correction across every test in the report: channels, roles, and holdout tests.
    tests = [(stp, r) for stp in steps for r in stp["incremental"]["channels"] + stp["incremental"]["roles"]]
    tests += [(stp, stp["incremental"]["program"]) for stp in steps if stp["incremental"]["program"]]
    if headline["_holdout_test"]:
        tests.append((None, headline["_holdout_test"]))
    m = max(1, len(tests))
    for (stp, r), pa in zip(tests, holm([r["p"] for _, r in tests])):
        r["p_adjusted"] = pa
        enough, more = sample_check(r["lift"], r["rate_control"], r["n_exposed"], r["n_control"], s["alpha"] / m, s["power"])
        n_now = stp["eligible"] if stp else r["n_exposed"] + r["n_control"]
        r["status"] = _status(pa, r.get("direction", r["lift"]), enough, more, n_now, s)
        r["more_accounts_needed"] = more if r["status"] == "not enough data yet" else 0
        r["extra_advances"] = r["lift"] * r["n_exposed"] if r["status"] == "lift" else 0.0
        if stp and "role" in r and r["status"] == "lift":
            stp["suggested_key_roles"].append(r["role"])

    for stp in steps:
        for row in stp["incremental"]["channels"] + stp["incremental"]["roles"]:
            row["value"] = row["extra_advances"] * value[stp["to"]] if row["status"] == "lift" else 0.0
            cost = s["channel_costs"].get(row.get("channel")) if "channel" in row else None
            row["cost"] = cost
            row["cost_per_extra_advance"] = (cost / row["extra_advances"]) if cost and row["status"] == "lift" and row["extra_advances"] > 0 else None
        prog = stp["incremental"]["program"]
        if prog:
            prog["value"] = prog["extra_advances"] * value[stp["to"]] if prog["status"] == "lift" else 0.0
        for row in stp["influenced"]["channels"] + stp["influenced"]["roles"]:
            row["pipeline"] = row["credited_advances"] * value[stp["to"]]

    _finish_headline(headline, steps, non_mkt, value)

    # Caused by marketing, per stage reached (estimated): extra advances into it from marketing channels.
    caused_into = {stp["to"]: sum(r["value"] for r in stp["incremental"]["channels"] if r["channel"] not in non_mkt)
                   for stp in steps}
    touched_ids = headline["touched_by_marketing"]["account_ids_any"]
    caused_ids = {stp["to"]: sorted({i for r in stp["incremental"]["channels"] if r["channel"] not in non_mkt and r["status"] == "lift" for i in r["exposed_ids"]})
                  for stp in steps}
    funnel = []
    for st in STAGES:
        reached = [a for a in accounts.values() if a["dates"][st]]
        stp = next((x for x in steps if x["from"] == st), None)
        funnel.append({
            "stage": st, "label": STAGE_LABELS[st], "accounts": len(reached),
            "advance_rate": stp["rate"] if stp else None, "judged": stp["eligible"] if stp else None,
            "value": value[st],
            "pipeline": sum(a["pipeline"] for a in reached),
            "started_by_marketing": sum(a["pipeline"] for a in reached if a["source"] and a["source"] not in non_mkt),
            "touched_by_marketing": sum(a["pipeline"] for a in reached if a["id"] in touched_ids),
            "caused_by_marketing": caused_into.get(st, 0.0),
            "won": sum(a["won"] for a in reached),
            "account_ids": [a["id"] for a in reached],
            "judged_ids": [r["account_id"] for r in stp["accounts"]] if stp else [],
            "pipeline_ids": [a["id"] for a in reached if a["pipeline"]],
            "started_ids": [a["id"] for a in reached if a["pipeline"] and a["source"] and a["source"] not in non_mkt],
            "touched_ids": [a["id"] for a in reached if a["pipeline"] and a["id"] in touched_ids],
            "caused_ids": caused_ids.get(st, []),
            "won_ids": [a["id"] for a in reached if a["won"]],
        })

    sourced = {}
    for a in accounts.values():
        if a["source"] and a["source"] not in non_mkt:
            row = sourced.setdefault(a["source"], {"channel": a["source"], "accounts": 0, "opportunities": 0,
                                                   "pipeline": 0.0, "won": 0.0, "account_ids": []})
            row["accounts"] += 1
            row["opportunities"] += 1 if a["dates"]["opportunity"] else 0
            row["pipeline"] += a["pipeline"]
            row["won"] += a["won"]
            row["account_ids"].append(a["id"])
            if a["dates"]["opportunity"]:
                row.setdefault("opportunity_ids", []).append(a["id"])

    open_deal = {d["account_id"] for d in tables.get("deals", []) if d.get("status") in ("open", "won")}
    lost = {a["id"] for a in accounts.values() if a["dates"]["opportunity"] and a["id"] not in open_deal}
    gaps = _gaps(accounts, touches, s, as_of, windows, lost)
    del headline["_holdout_test"]
    headline["touched_by_marketing"].pop("account_ids_any")
    return {
        "tool": "Account Hub", "version": 1, "as_of": as_of.isoformat(),
        "touch_history_start": history_start.isoformat(),
        "settings": s,
        "headline": headline,
        "funnel": funnel,
        "steps": steps,
        "sourced_by_channel": sorted(sourced.values(), key=lambda r: -r["pipeline"]),
        "gaps": gaps,
        "accounts": [{"account_id": a["id"], "name": a["name"], "segment": a["segment"],
                      "holdout": a["holdout"], "original_source": a["source"],
                      "stage": STAGE_LABELS.get(_current(a), ""),
                      "pipeline": a["pipeline"], "won": a["won"],
                      "dates": {k: (v.isoformat() if v else None) for k, v in a["dates"].items()}}
                     for a in sorted(accounts.values(), key=lambda a: a["name"])],
    }


def _step(frm, to, window, wsource, accounts, touches, s, as_of, history_start, non_mkt):
    rows = []
    for a in accounts.values():
        start = a["dates"][frm]
        if not start or start < history_start:
            continue                      # no touch history covers this account's window
        if window and start + timedelta(days=window) > as_of:
            continue                      # window not over yet: too early to judge
        adv = _later(a, frm)
        limit = start + timedelta(days=window) if window else as_of   # last day that counts
        advanced = adv is not None and adv <= limit
        end = adv if advanced else limit + timedelta(days=1)          # touches before the advance
        in_window = [t for t in touches.get(a["id"], []) if start <= t["date"] < end]
        key = _key_roles(s, frm, a["segment"])
        engaged = [t for t in in_window if t["kind"] == "engaged"]
        roles_engaged = sorted({t["role"] for t in engaged if t["role"]})
        covered = [r for r in key if r in roles_engaged]
        rows.append({"account_id": a["id"], "name": a["name"], "segment": a["segment"], "holdout": a["holdout"],
                     "cohort": start.strftime("%Y-%m"), "advanced": advanced,
                     "depth": "Engaged" if engaged else ("Reached" if in_window else "Not reached"),
                     "coverage": "None" if not covered else ("1 role" if len(covered) == 1 else "2+ roles"),
                     "channels_engaged": sorted({t["channel"] for t in engaged}),
                     "channels_reached_only": sorted({t["channel"] for t in in_window if t["kind"] == "reached"} - {t["channel"] for t in engaged}),
                     "roles_engaged": roles_engaged, "key_roles": key,
                     "missing_roles": [r for r in key if r not in roles_engaged],
                     "_engaged": engaged, "_won": a["won"]})

    n = len(rows)
    adv_n = sum(r["advanced"] for r in rows)
    grid = []
    for dpt in DEPTHS:
        for cov in COVERAGE:
            cell = [r for r in rows if r["depth"] == dpt and r["coverage"] == cov]
            k = sum(r["advanced"] for r in cell)
            grid.append({"depth": dpt, "coverage": cov, "accounts": len(cell), "advanced": k,
                         "rate": (k / len(cell)) if cell else None, "account_ids": [r["account_id"] for r in cell]})

    # Touched by marketing (influenced): an advance gives equal credit to every engaged
    # marketing touch in its window. Credit, not proof.
    ch, rl = {}, {}
    touched = []
    for r in rows:
        mk = [t for t in r["_engaged"] if t["channel"] not in non_mkt]
        if not r["advanced"] or not mk:
            continue
        touched.append(r["account_id"])
        for t in mk:
            row = ch.setdefault(t["channel"], {"channel": t["channel"], "credited_advances": 0.0, "won": 0.0, "account_ids": set()})
            row["credited_advances"] += 1 / len(mk)
            row["won"] += r["_won"] / len(mk)
            row["account_ids"].add(r["account_id"])
        with_role = [t for t in mk if t["role"]]
        for t in with_role:
            row = rl.setdefault(t["role"], {"role": t["role"], "credited_advances": 0.0, "won": 0.0, "account_ids": set()})
            row["credited_advances"] += 1 / len(with_role)
            row["won"] += r["_won"] / len(with_role)
            row["account_ids"].add(r["account_id"])
    fix = lambda d: [{**v, "account_ids": sorted(v["account_ids"])} for v in sorted(d.values(), key=lambda v: -v["credited_advances"])]
    influenced = {"channels": fix(ch), "roles": fix(rl), "influenced_advances": len(touched), "account_ids": touched}

    # Caused by marketing (incremental): every channel and role in one logistic regression with
    # segment and cohort, so each is judged with the others held fixed.
    tests = []
    for c in sorted({c for r in rows for c in r["channels_engaged"] + r["channels_reached_only"]}):
        tests.append(("channel", c, "engaged", lambda r, c=c: c in r["channels_engaged"]))
        if any(c in r["channels_reached_only"] for r in rows):
            tests.append(("channel", c, "reached only", lambda r, c=c: c in r["channels_reached_only"]))
    for role in sorted({x for r in rows for x in r["roles_engaged"]}):
        tests.append(("role", role, "engaged", lambda r, role=role: role in r["roles_engaged"]))
    segments = sorted({r["segment"] for r in rows})
    cohorts = sorted({r["cohort"] for r in rows})
    results = []
    usable = [t for t in tests if 0 < sum(1 for r in rows if t[3](r)) < len(rows)]
    if rows and usable and 0 < adv_n < len(rows):
        base = len(segments) + len(cohorts) - 1

        def design(r, override=None):
            x = [1.0] + [1.0 if r["segment"] == g else 0.0 for g in segments[1:]] + \
                [1.0 if r["cohort"] == c else 0.0 for c in cohorts[1:]]
            for idx, t in enumerate(usable):
                x.append(override[1] if override and override[0] == idx else (1.0 if t[3](r) else 0.0))
            return x
        coef, se = logit([design(r) for r in rows], [1.0 if r["advanced"] else 0.0 for r in rows])
        for idx, (kind, name, exposure, fn) in enumerate(usable):
            exposed = [r for r in rows if fn(r)]
            if exposure == "reached only":   # compare with accounts this channel never touched
                control = [r for r in rows if name not in r["channels_engaged"] and name not in r["channels_reached_only"]]
            else:
                control = [r for r in rows if not fn(r)]
            # Lift in points: for the exposed accounts, modeled advance rate with vs without it.
            lift = sum(predict(coef, design(r, (idx, 1.0))) - predict(coef, design(r, (idx, 0.0))) for r in exposed) / len(exposed)
            results.append({kind: name, "exposure": exposure, "lift": lift, "p": wald_p(coef[base + idx], se[base + idx]),
                            "n_exposed": len(exposed), "n_control": len(control),
                            "rate_exposed": sum(r["advanced"] for r in exposed) / len(exposed),
                            "rate_control": (sum(r["advanced"] for r in control) / len(control)) if control else 0.0,
                            "label": "estimated", "exposed_ids": [r["account_id"] for r in exposed]})

    # Program vs holdout list, exact, within segment x cohort.
    program = None
    if any(r["holdout"] for r in rows) and any(not r["holdout"] for r in rows):
        strata = []
        for g in segments:
            for c in cohorts:
                ex = [r for r in rows if r["segment"] == g and r["cohort"] == c and not r["holdout"]]
                co = [r for r in rows if r["segment"] == g and r["cohort"] == c and r["holdout"]]
                strata.append((len(ex), sum(r["advanced"] for r in ex), len(co), sum(r["advanced"] for r in co)))
        program = exact_stratified(strata)
        if program:
            program["label"] = "tested against holdout"
            program["exposed_ids"] = [r["account_id"] for r in rows if not r["holdout"]]

    for r in rows:
        del r["_engaged"], r["_won"]
    return {"from": frm, "to": to, "step": f"{frm}->{to}",
            "label": f"{STAGE_LABELS[frm]} → {STAGE_LABELS[to]}",
            "window_days": window, "window_source": wsource,
            "eligible": n, "advanced": adv_n, "rate": (adv_n / n) if n else None,
            "grid": grid, "influenced": influenced,
            "incremental": {"program": program,
                            "channels": [r for r in results if "channel" in r],
                            "roles": [r for r in results if "role" in r]},
            "suggested_key_roles": [], "accounts": rows}


def _gaps(accounts, touches, s, as_of, windows, lost):
    """Every target account still in play (not holdout, not yet won), at its current stage:
    the key roles for its next step that haven't engaged since it reached that stage. This is the
    to-do list the Activations tab works from."""
    out = []
    for a in sorted(accounts.values(), key=lambda a: a["name"]):
        cur = _current(a)
        if a["holdout"] or cur in (None, "closed_won") or a["id"] in lost:
            continue
        since = a["dates"][cur]
        engaged = {t["role"] for t in touches.get(a["id"], []) if t["kind"] == "engaged" and t["role"] and since <= t["date"] <= as_of}
        nxt = STAGES[STAGES.index(cur) + 1]
        for role in _key_roles(s, cur, a["segment"]):
            if role not in engaged:
                out.append({"account_id": a["id"], "name": a["name"], "segment": a["segment"],
                            "stage": STAGE_LABELS[cur], "step": f"{STAGE_LABELS[cur]} → {STAGE_LABELS[nxt]}",
                            "missing_role": role, "days_at_stage": (as_of - since).days,
                            # Past twice the usual time at this stage: likely stalled, worth a look first.
                            "stalled": bool(windows.get(cur)) and (as_of - since).days > 2 * windows[cur]})
    return out


def _status(p, lift, enough, more, n, s):
    """lift / negative when the test is clear; otherwise say whether more data could settle it.
    A lift so small that it would take more than `max_more_multiple` times today's accounts
    to confirm is reported as no lift found: it's too small to act on."""
    if p < s["alpha"]:
        return "lift" if lift > 0 else "negative"
    if enough or more > s["max_more_multiple"] * n:
        return "no lift found"
    return "not enough data yet"


def _headline(accounts, steps, non_mkt, s, windows, as_of, history_start):
    opp = [a for a in accounts.values() if a["dates"]["opportunity"]]
    won = [a for a in accounts.values() if a["dates"]["closed_won"]]
    sourced = [a for a in opp if a["source"] and a["source"] not in non_mkt]
    # Touched: the account advanced on its way to Opportunity with an engaged marketing touch
    # in that step's window.
    touched_any = {i for stp in steps if stp["to"] in ("hand_raiser", "sql", "opportunity") for i in stp["influenced"]["account_ids"]}
    touched = [a for a in opp if a["id"] in touched_any]
    # Holdout: did program accounts become Opportunities more often than holdout accounts? Only
    # accounts the program could still act on count (they entered the funnel before SQL, inside the
    # touch history), once every window up to Opportunity has passed; compared within segment x cohort.
    test = None
    span = [windows[x] for x in ("nhr_lead", "hand_raiser", "sql")]
    wait = sum(span) if all(span) else None
    pool = []
    for a in accounts.values():
        entry = next((st for st in STAGES if a["dates"][st]), None)
        if entry not in ("nhr_lead", "hand_raiser"):
            continue
        start = a["dates"][entry]
        if start < history_start or (wait and start + timedelta(days=wait) > as_of):
            continue
        pool.append((a, start.strftime("%Y-%m")))
    if any(a["holdout"] for a, _ in pool) and any(not a["holdout"] for a, _ in pool):
        strata = []
        for g in sorted({a["segment"] for a, _ in pool}):
            for c in sorted({c for _, c in pool}):
                ex = [a for a, k in pool if a["segment"] == g and k == c and not a["holdout"]]
                co = [a for a, k in pool if a["segment"] == g and k == c and a["holdout"]]
                strata.append((len(ex), sum(1 for a in ex if a["dates"]["opportunity"]), len(co), sum(1 for a in co if a["dates"]["opportunity"])))
        test = exact_stratified(strata)
        if test:
            test["exposed_ids"] = [a["id"] for a, _ in pool if not a["holdout"]]
    ids = lambda xs: [a["id"] for a in xs]
    return {
        "pipeline_total": sum(a["pipeline"] for a in opp), "won_total": sum(a["won"] for a in won),
        "opportunities": len(opp), "closed_won": len(won), "win_rate": (len(won) / len(opp)) if opp else None,
        "opportunity_ids": ids(opp), "won_ids": ids(won),
        "started_by_marketing": {"opportunities": len(sourced), "pipeline": sum(a["pipeline"] for a in sourced),
                                 "won": sum(a["won"] for a in sourced), "account_ids": ids(sourced)},
        "touched_by_marketing": {"opportunities": len(touched), "pipeline": sum(a["pipeline"] for a in touched),
                                 "won": sum(a["won"] for a in touched), "account_ids": ids(touched),
                                 "account_ids_any": touched_any},
        "_holdout_test": test,
    }


def _finish_headline(h, steps, non_mkt, value):
    test = h["_holdout_test"]
    if test:
        test["incremental_pipeline"] = test["lift"] * test["n_exposed"] * value["opportunity"] if test["status"] == "lift" else 0.0
        h["caused_by_marketing"] = {"pipeline": test["incremental_pipeline"], "label": "tested against holdout",
                                    "status": test["status"], "holdout": {k: v for k, v in test.items() if k != "exposed_ids"},
                                    "account_ids": test["exposed_ids"] if test["status"] == "lift" else []}
        return
    # No holdout: marketing channels' extra advances on the way to Opportunity, each valued at the
    # pipeline its stage is worth. Estimated.
    rows = [(stp, r) for stp in steps if stp["to"] in ("hand_raiser", "sql", "opportunity")
            for r in stp["incremental"]["channels"] if r["channel"] not in non_mkt and r["status"] == "lift"]
    total = sum(r["value"] for _, r in rows)
    h["caused_by_marketing"] = {"pipeline": total, "label": "estimated, steps added together", "status": "lift" if total > 0 else "no lift found",
                                "holdout": None, "account_ids": sorted({i for _, r in rows for i in r["exposed_ids"]})}
