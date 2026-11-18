"""Results as flat tables: the Google Sheet's results tabs read these."""
import csv
import os


def tables(res):
    h = res["headline"]
    summary = [
        {"measure": "Pipeline", "value": h["pipeline_total"]},
        {"measure": "Pipeline started by marketing (sourced)", "value": h["started_by_marketing"]["pipeline"]},
        {"measure": "Pipeline touched by marketing (influenced)", "value": h["touched_by_marketing"]["pipeline"]},
        {"measure": f"Pipeline caused by marketing (incremental, {h['caused_by_marketing']['label']})", "value": h["caused_by_marketing"]["pipeline"]},
        {"measure": "Won", "value": h["won_total"]},
        {"measure": "Win rate", "value": h["win_rate"]},
    ]
    funnel = [{k: f[k] for k in ("label", "accounts", "advance_rate", "value")} for f in res["funnel"]]
    grid, caused, touched = [], [], []
    for st in res["steps"]:
        for c in st["grid"]:
            grid.append({"step": st["label"], "reach": c["depth"], "coverage": c["coverage"],
                         "accounts": c["accounts"], "advanced": c["advanced"], "advance_rate": c["rate"]})
        for x in st["incremental"]["channels"] + st["incremental"]["roles"]:
            caused.append({"step": st["label"], "channel_or_role": x.get("channel") or x.get("role"),
                           "exposure": x["exposure"], "status": x["status"], "lift_points": round(x["lift"] * 100, 1),
                           "accounts_exposed": x["n_exposed"], "extra_advances": x["extra_advances"],
                           "pipeline": x.get("value"), "more_accounts_needed": x["more_accounts_needed"]})
        for x in st["influenced"]["channels"]:
            touched.append({"step": st["label"], "channel": x["channel"],
                            "credited_advances": x["credited_advances"], "pipeline": x.get("pipeline")})
    return {"summary": summary, "funnel": funnel, "step_grid": grid, "caused_by_marketing": caused,
            "touched_by_marketing": touched, "started_by_marketing": res["sourced_by_channel"],
            "gaps": res["gaps"],
            "accounts": [{k: v for k, v in a.items() if k != "dates"} for a in res["accounts"]]}


def write_csv(res, folder):
    os.makedirs(folder, exist_ok=True)
    for name, rows in tables(res).items():
        with open(os.path.join(folder, f"{name}.csv"), "w", newline="") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
