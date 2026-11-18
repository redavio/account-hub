"""ABM Analyzer engine: four tables in, one results file out.

Tables (same columns as the Google Sheet template; HubSpot is read into the same shape):
  accounts: account_id, name, segment, target, holdout, original_source,
            nhr_lead_date, hand_raiser_date, sql_date
  contacts: contact_id, account_id, name, role
  deals:    deal_id, account_id, amount, created_date, status (open|won|lost), close_date
  touches:  touch_id, account_id, contact_id, date, channel, kind (engaged|reached), detail

Opportunity date = first deal created; Closed won date = first won deal's close date.
"""
from datetime import date, timedelta

from .stats import holm, logit, predict, sample_check, stratified_lift, wald_p

STAGES = ["nhr_lead", "hand_raiser", "sql", "opportunity", "closed_won"]
STAGE_LABELS = {"nhr_lead": "Non-hand-raiser lead", "hand_raiser": "Hand-raiser", "sql": "SQL",
                "opportunity": "Opportunity", "closed_won": "Closed won"}
DEPTHS = ["Not reached", "Reached", "Engaged"]
COVERAGE = ["None", "1 role", "2+ roles"]

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
    "non_marketing_channels": ["sales outreach"],
    "channel_costs": {},                 # channel -> cost over the period
    "alpha": 0.05,
    "power": 0.8,
    "max_more_multiple": 10,             # beyond 10x today's accounts, a lift is too small to act on
}


def _d(s):
    return date.fromisoformat(s) if s else None


def _settings(user):
    s = {**DEFAULTS, **(user or {})}
    s["key_roles"] = {**DEFAULTS["key_roles"], **(user or {}).get("key_roles", {})}
    return s


def _prepare(tables):
    accounts = {}
    for a in tables["accounts"]:
        if str(a.get("target", "yes")).strip().lower() not in ("yes", "true", "1", "y"):
            continue
        accounts[a["account_id"]] = {
            "id": a["account_id"], "name": a.get("name", a["account_id"]),
            "segment": a.get("segment") or "All", "holdout": str(a.get("holdout", "")).strip().lower() in ("yes", "true", "1", "y"),
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
                "kind": "engaged" if t.get("kind") == "engaged" else "reached",
                "role": roles.get(t.get("contact_id"), "")})
    return accounts, touches


def _later(a, stage):
    """First date the account reached any stage after `stage`."""
    i = STAGES.index(stage)
    ds = [a["dates"][s] for s in STAGES[i + 1:] if a["dates"][s]]
    return min(ds) if ds else None


def _percentile(xs, q):
    """Nearest rank: the smallest value with at least q of the list at or below it."""
    from math import ceil
    xs = sorted(xs)
    return xs[max(0, min(len(xs) - 1, ceil(q * len(xs)) - 1))]


def analyze(tables, settings=None):
    s = _settings(settings)
    accounts, touches = _prepare(tables)
    all_dates = [t["date"] for ts in touches.values() for t in ts] + \
        [d for a in accounts.values() for d in a["dates"].values() if d]
    as_of = _d(s["as_of"]) if s["as_of"] else max(all_dates)
    history_start = min((t["date"] for ts in touches.values() for t in ts), default=as_of)
    non_mkt = set(s["non_marketing_channels"])

    # Value of each stage in pipeline $: share that become an Opportunity x average Opportunity.
    opp_amounts = [a["pipeline"] for a in accounts.values() if a["dates"]["opportunity"]]
    avg_opp = sum(opp_amounts) / len(opp_amounts) if opp_amounts else 0.0
    won_amounts = [a["won"] for a in accounts.values() if a["dates"]["closed_won"]]
    avg_won = sum(won_amounts) / len(won_amounts) if won_amounts else 0.0

    steps, windows = [], {}
    for i, frm in enumerate(STAGES[:-1]):
        to = STAGES[i + 1]
        durations = [(_later(a, frm) - a["dates"][frm]).days for a in accounts.values()
                     if a["dates"][frm] and _later(a, frm)]
        if len(durations) >= s["min_history_for_window"]:
            window, wsource = max(1, _percentile(durations, s["window_percentile"])), "history"
        elif s["sales_cycle_days"]:
            window, wsource = int(s["sales_cycle_days"]), "sales cycle setting"
        else:
            window, wsource = None, "whole time at the stage"
        windows[frm] = window
        steps.append(_step(frm, to, window, wsource, accounts, touches, s, as_of, history_start, non_mkt))

    # One correction across every channel and role test in the report, so the chance of any
    # false "lift" anywhere stays at alpha.
    pairs = [(stp, r) for stp in steps for r in stp["incremental"]["channels"] + stp["incremental"]["roles"]]
    for (stp, r), pa in zip(pairs, holm([r["p"] for _, r in pairs])):
        r["p_adjusted"] = pa
        enough, more = sample_check(r["lift"], r["rate_control"], r["n_exposed"], r["n_control"], s["alpha"], s["power"])
        r["status"] = _status(pa, r["lift"], enough, more, stp["eligible"], s)
        r["more_accounts_needed"] = more if r["status"] == "not enough data yet" else 0
        r["extra_advances"] = r["lift"] * r["n_exposed"] if r["status"] == "lift" else 0.0
        r["label"] = "estimated"
        if "role" in r and r["status"] == "lift":
            stp["suggested_key_roles"].append(r["role"])

    value = {}
    for st in STAGES:
        if st == "opportunity":
            value[st] = avg_opp
        elif st == "closed_won":
            value[st] = avg_won
        else:
            matured = [a for a in accounts.values() if a["dates"][st]
                       and (windows.get(st) is None or a["dates"][st] + timedelta(days=windows[st]) <= as_of)]
            reached_opp = sum(1 for a in matured if a["dates"]["opportunity"])
            value[st] = (reached_opp / len(matured) * avg_opp) if matured else 0.0

    # Extra advances x value of the stage reached = incremental pipeline $ (per channel).
    for stp in steps:
        for row in stp["incremental"]["channels"] + stp["incremental"]["roles"]:
            row["value"] = row["extra_advances"] * value[stp["to"]] if row["status"] == "lift" else 0.0
            cost = s["channel_costs"].get(row.get("channel")) if "channel" in row else None
            row["cost"] = cost
            row["cost_per_extra_advance"] = (cost / row["extra_advances"]) if cost and row["status"] == "lift" and row["extra_advances"] > 0 else None
        for row in stp["influenced"]["channels"] + stp["influenced"]["roles"]:
            row["pipeline"] = row["credited_advances"] * value[stp["to"]]

    funnel = []
    for st in STAGES:
        reached = [a for a in accounts.values() if a["dates"][st]]
        stp = next((x for x in steps if x["from"] == st), None)
        funnel.append({"stage": st, "label": STAGE_LABELS[st], "accounts": len(reached),
                       "advance_rate": stp["rate"] if stp else None,
                       "eligible": stp["eligible"] if stp else None,
                       "value": value[st], "account_ids": [a["id"] for a in reached]})

    headline = _headline(accounts, touches, steps, non_mkt, s)
    gaps = [g for stp in steps for g in stp.pop("_gaps")]
    sourced = {}
    for a in accounts.values():
        if a["source"] and a["source"] not in non_mkt:
            row = sourced.setdefault(a["source"], {"channel": a["source"], "accounts": 0, "opportunities": 0, "pipeline": 0.0, "won": 0.0})
            row["accounts"] += 1
            row["opportunities"] += 1 if a["dates"]["opportunity"] else 0
            row["pipeline"] += a["pipeline"]
            row["won"] += a["won"]

    return {
        "tool": "ABM Analyzer", "version": 1, "as_of": as_of.isoformat(),
        "touch_history_start": history_start.isoformat(),
        "settings": {k: v for k, v in s.items()},
        "headline": headline,
        "funnel": funnel,
        "steps": steps,
        "sourced_by_channel": sorted(sourced.values(), key=lambda r: -r["pipeline"]),
        "gaps": gaps,
        "accounts": [{"account_id": a["id"], "name": a["name"], "segment": a["segment"],
                      "holdout": a["holdout"], "original_source": a["source"],
                      "stage": next((STAGE_LABELS[st] for st in reversed(STAGES) if a["dates"][st]), ""),
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
            continue                      # window not over yet: too early to judge (cohort rule)
        adv = _later(a, frm)
        advanced = adv is not None and adv <= as_of
        end = start + timedelta(days=window) if window else as_of + timedelta(days=1)
        if advanced and adv < end:
            end = adv
        in_window = [t for t in touches.get(a["id"], []) if start <= t["date"] < end]
        key = list(s["key_roles"].get(frm, []))
        if a["segment"] == s["enterprise_segment"]:
            key += s["enterprise_extra_roles"].get(frm, [])
        engaged = [t for t in in_window if t["kind"] == "engaged"]
        roles_engaged = sorted({t["role"] for t in engaged if t["role"]})
        covered = [r for r in key if r in roles_engaged]
        depth = "Engaged" if engaged else ("Reached" if in_window else "Not reached")
        cov = "None" if not covered else ("1 role" if len(covered) == 1 else "2+ roles")
        rows.append({"account_id": a["id"], "name": a["name"], "segment": a["segment"], "holdout": a["holdout"],
                     "advanced": advanced, "depth": depth, "coverage": cov,
                     "channels_engaged": sorted({t["channel"] for t in engaged}),
                     "channels_reached_only": sorted({t["channel"] for t in in_window if t["kind"] == "reached"} - {t["channel"] for t in engaged}),
                     "roles_engaged": roles_engaged, "key_roles": key,
                     "missing_roles": [r for r in key if r not in roles_engaged],
                     "_engaged": engaged})

    n = len(rows)
    adv_n = sum(r["advanced"] for r in rows)
    grid = []
    for dpt in DEPTHS:
        for cov in COVERAGE:
            cell = [r for r in rows if r["depth"] == dpt and r["coverage"] == cov]
            k = sum(r["advanced"] for r in cell)
            grid.append({"depth": dpt, "coverage": cov, "accounts": len(cell), "advanced": k,
                         "rate": (k / len(cell)) if cell else None, "account_ids": [r["account_id"] for r in cell]})

    # Touched by marketing (influenced): equal credit to every engaged marketing touch.
    ch_credit, role_credit = {}, {}
    for r in rows:
        if not r["advanced"]:
            continue
        mk = [t for t in r["_engaged"] if t["channel"] not in non_mkt]
        for t in mk:
            ch_credit[t["channel"]] = ch_credit.get(t["channel"], 0) + 1 / len(mk)
        eng_roles = [t["role"] for t in r["_engaged"] if t["role"]]
        for role in eng_roles:
            role_credit[role] = role_credit.get(role, 0) + 1 / len(eng_roles)
    influenced = {
        "channels": [{"channel": c, "credited_advances": v} for c, v in sorted(ch_credit.items(), key=lambda x: -x[1])],
        "roles": [{"role": c, "credited_advances": v} for c, v in sorted(role_credit.items(), key=lambda x: -x[1])],
        "influenced_advances": sum(1 for r in rows if r["advanced"] and any(t["channel"] not in non_mkt for t in r["_engaged"])),
    }

    # Caused by marketing (incremental): exposed vs not, within segment, target accounts.
    tests = []
    channels = sorted({c for r in rows for c in r["channels_engaged"] + r["channels_reached_only"]})
    for c in channels:
        tests.append(("channel", c, "engaged", lambda r, c=c: c in r["channels_engaged"]))
        if any(c in r["channels_reached_only"] for r in rows):
            tests.append(("channel", c, "reached only", lambda r, c=c: c in r["channels_reached_only"]))
    for role in sorted({x for r in rows for x in r["roles_engaged"]}):
        tests.append(("role", role, "engaged", lambda r, role=role: role in r["roles_engaged"]))
    # Each factor is tested while holding the others fixed (logistic regression on every
    # channel and role at once, plus segment). Without this, a role looks like it works
    # just because that person also clicked the ad that did the work.
    segments = sorted({r["segment"] for r in rows})
    results = []
    usable = [t for t in tests if 0 < sum(1 for r in rows if t[3](r)) < len(rows)]
    if rows and usable and 0 < adv_n < len(rows):
        def design(r, override=None):
            x = [1.0] + [1.0 if r["segment"] == seg else 0.0 for seg in segments[1:]]
            for idx, t in enumerate(usable):
                x.append(override[1] if override and override[0] == idx else (1.0 if t[3](r) else 0.0))
            return x
        X = [design(r) for r in rows]
        y = [1.0 if r["advanced"] else 0.0 for r in rows]
        coef, se = logit(X, y)
        off = len(segments)
        for idx, (kind, name, exposure, fn) in enumerate(usable):
            exposed = [r for r in rows if fn(r)]
            if exposure == "reached only":
                control = [r for r in rows if name not in r["channels_engaged"] and name not in r["channels_reached_only"]]
            else:
                control = [r for r in rows if not fn(r)]
            # Lift in points: for the exposed accounts, modeled advance rate with vs without it.
            lift = sum(predict(coef, design(r, (idx, 1.0))) - predict(coef, design(r, (idx, 0.0))) for r in exposed) / len(exposed)
            results.append({kind: name, "exposure": exposure, "lift": lift,
                            "p": wald_p(coef[off + idx], se[off + idx]),
                            "n_exposed": len(exposed), "n_control": len(control),
                            "rate_exposed": sum(r["advanced"] for r in exposed) / len(exposed),
                            "rate_control": (sum(r["advanced"] for r in control) / len(control)) if control else 0.0})

    # Program-level test against the holdout list, when there is one.
    program = None
    if any(r["holdout"] for r in rows) and any(not r["holdout"] for r in rows):
        strata = []
        for seg in segments:
            ex = [r for r in rows if r["segment"] == seg and not r["holdout"]]
            co = [r for r in rows if r["segment"] == seg and r["holdout"]]
            strata.append((len(ex), sum(r["advanced"] for r in ex), len(co), sum(r["advanced"] for r in co)))
        program = stratified_lift(strata)
        if program:
            enough, more = sample_check(program["lift"], program["rate_control"], program["n_exposed"], program["n_control"], s["alpha"], s["power"])
            program["status"] = _status(program["p"], program["lift"], enough, more, n, s)
            program["more_accounts_needed"] = more if program["status"] == "not enough data yet" else 0
            program["label"] = "tested against holdout"


    gaps = []
    for r in rows:
        if not r["advanced"]:
            for role in r["missing_roles"]:
                gaps.append({"account_id": r["account_id"], "name": r["name"], "step": f"{frm}->{to}",
                             "missing_role": role})
    for r in rows:
        del r["_engaged"]

    return {"from": frm, "to": to, "step": f"{frm}->{to}",
            "label": f"{STAGE_LABELS[frm]} → {STAGE_LABELS[to]}",
            "window_days": window, "window_source": wsource,
            "eligible": n, "advanced": adv_n, "rate": (adv_n / n) if n else None,
            "grid": grid, "influenced": influenced,
            "incremental": {"program": program,
                            "channels": [r for r in results if "channel" in r],
                            "roles": [r for r in results if "role" in r]},
            "suggested_key_roles": [], "accounts": rows, "_gaps": gaps}


def _status(p, lift, enough, more, n, s):
    """lift / negative when the test is clear; otherwise say whether more data could settle it.
    A lift so small that it would take more than `max_more_multiple` times today's accounts
    to confirm is reported as no lift found: it's too small to act on."""
    if p < s["alpha"]:
        return "lift" if lift > 0 else "negative"
    if enough or more > s["max_more_multiple"] * n:
        return "no lift found"
    return "not enough data yet"


def _headline(accounts, touches, steps, non_mkt, s):
    opp = [a for a in accounts.values() if a["dates"]["opportunity"]]
    won = [a for a in accounts.values() if a["dates"]["closed_won"]]
    sourced = [a for a in opp if a["source"] and a["source"] not in non_mkt]
    influenced = []
    for a in opp:
        before = [t for t in touches.get(a["id"], []) if t["kind"] == "engaged"
                  and t["channel"] not in non_mkt and t["date"] < a["dates"]["opportunity"]]
        if before:
            influenced.append(a)
    incr_value = sum(r["value"] for stp in steps for r in stp["incremental"]["channels"])
    # Holdout: share of accounts that became an Opportunity, program vs holdout, within segment.
    holdout_view = None
    if any(a["holdout"] for a in accounts.values()) and any(not a["holdout"] for a in accounts.values()):
        segs = sorted({a["segment"] for a in accounts.values()})
        strata = []
        for seg in segs:
            ex = [a for a in accounts.values() if a["segment"] == seg and not a["holdout"]]
            co = [a for a in accounts.values() if a["segment"] == seg and a["holdout"]]
            strata.append((len(ex), sum(1 for a in ex if a["dates"]["opportunity"]),
                           len(co), sum(1 for a in co if a["dates"]["opportunity"])))
        test = stratified_lift(strata)
        if test:
            enough, more = sample_check(test["lift"], test["rate_control"], test["n_exposed"], test["n_control"], s["alpha"], s["power"])
            status = _status(test["p"], test["lift"], enough, more, test["n_exposed"] + test["n_control"], s)
            avg_opp = (sum(a["pipeline"] for a in opp) / len(opp)) if opp else 0.0
            holdout_view = {**test, "status": status,
                            "more_accounts_needed": more if status == "not enough data yet" else 0,
                            "incremental_pipeline": test["lift"] * test["n_exposed"] * avg_opp if status == "lift" else 0.0}
    return {
        "pipeline_total": sum(a["pipeline"] for a in opp),
        "won_total": sum(a["won"] for a in won),
        "opportunities": len(opp), "closed_won": len(won),
        "win_rate": (len(won) / len(opp)) if opp else None,
        "started_by_marketing": {"opportunities": len(sourced), "pipeline": sum(a["pipeline"] for a in sourced),
                                 "won": sum(a["won"] for a in sourced)},
        "touched_by_marketing": {"opportunities": len(influenced), "pipeline": sum(a["pipeline"] for a in influenced),
                                 "won": sum(a["won"] for a in influenced)},
        "caused_by_marketing": ({"pipeline": holdout_view["incremental_pipeline"], "label": "tested against holdout",
                                 "status": holdout_view["status"], "holdout": holdout_view} if holdout_view else
                                {"pipeline": incr_value, "label": "estimated", "status": "lift" if incr_value > 0 else "no lift found", "holdout": None}),
    }
