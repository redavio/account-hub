"""Write the fictional demo data into a HubSpot TEST account.

  HUBSPOT_TOKEN=... python3 seed/hubspot_seed.py --portal <test portal id> [--reset]

Refuses to run unless the token's portal matches --portal, so it can't touch a real account.
--reset archives earlier demo records, and every meeting and email in the portal: test accounts only.
Writes: custom properties, companies, contacts, deals, meetings, email replies and marketing
event attendance. Touches HubSpot's API can't hold (web visits, ad clicks and impressions,
marketing emails sent) go to seed/demo-extra-touches.csv, the Sheet's extra touches tab.
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accounthub.hubspot import SOURCE_MAP, HubSpot  # noqa: E402
from generate import ROLES, generate  # noqa: E402

GROUP = "account_hub"
TO_SOURCE = {v: k for k, v in SOURCE_MAP.items()}
NATIVE = {"meeting", "email reply", "event attendance"}


def ms(day, hour=15):
    d = datetime.fromisoformat(day).replace(hour=hour, tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


def ensure_properties(hs):
    for obj in ("companies", "contacts", "deals"):
        try:
            hs.call("POST", f"/crm/v3/properties/{obj}/groups", {"name": GROUP, "label": "Account Hub"})
        except RuntimeError as e:
            if "409" not in str(e):
                raise
    yesno = [{"label": "Yes", "value": "true", "displayOrder": 0}, {"label": "No", "value": "false", "displayOrder": 1}]
    props = {
        "companies": [
            ("account_hub_id", "Account Hub demo id", "string", "text", None),
            ("account_hub_target", "ABM target", "enumeration", "booleancheckbox", yesno),
            ("account_hub_holdout", "ABM holdout", "enumeration", "booleancheckbox", yesno),
            ("account_hub_segment", "Segment", "enumeration", "select",
             [{"label": s, "value": s, "displayOrder": i} for i, s in enumerate(["SMB", "Mid-market", "Enterprise"])]),
            ("account_hub_nhr_lead_date", "Became a lead (non-hand-raiser)", "date", "date", None),
            ("account_hub_hand_raiser_date", "Became a hand-raiser", "date", "date", None),
            ("account_hub_sql_date", "Became an SQL", "date", "date", None),
        ],
        "contacts": [
            ("account_hub_id", "Account Hub demo id", "string", "text", None),
            ("account_hub_role", "Buying committee role", "enumeration", "select",
             [{"label": r, "value": r, "displayOrder": i} for i, r in enumerate(ROLES)]),
        ],
        "deals": [("account_hub_id", "Account Hub demo id", "string", "text", None)],
    }
    for obj, items in props.items():
        for name, label, typ, field, options in items:
            body = {"name": name, "label": label, "type": typ, "fieldType": field, "groupName": GROUP}
            if options:
                body["options"] = options
            try:
                hs.call("POST", f"/crm/v3/properties/{obj}", body)
            except RuntimeError as e:
                if "409" not in str(e):
                    raise


def batch_create(hs, obj, rows, links=None):
    """links[i] = [(to_object_id, association_type_id), ...] made in the same call, so nothing
    depends on HubSpot returning results in input order."""
    ids = []
    for i in range(0, len(rows), 100):
        inputs = []
        for j, p in enumerate(rows[i:i + 100]):
            item = {"properties": p}
            if links:
                item["associations"] = [{"to": {"id": to}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": t}]}
                                        for to, t in links[i + j]]
            inputs.append(item)
        r = hs.call("POST", f"/crm/v3/objects/{obj}/batch/create", {"inputs": inputs})
        # Results are not guaranteed in input order: map back by our demo id when present.
        ids += r["results"]
        print(f"  {obj}: {min(i + 100, len(rows))}/{len(rows)}", flush=True)
    return ids


def associate(hs, frm, to, pairs):
    for i in range(0, len(pairs), 100):
        hs.call("POST", f"/crm/v4/associations/{frm}/{to}/batch/associate/default",
                {"inputs": [{"from": {"id": a}, "to": {"id": b}} for a, b in pairs[i:i + 100]]})


def existing(hs, obj):
    out, after = [], None
    while True:
        body = {"filterGroups": [{"filters": [{"propertyName": "account_hub_id", "operator": "HAS_PROPERTY"}]}],
                "properties": ["account_hub_id"], "limit": 100}
        if after:
            body["after"] = after
        r = hs.call("POST", f"/crm/v3/objects/{obj}/search", body)
        out += [x["id"] for x in r.get("results", [])]
        after = r.get("paging", {}).get("next", {}).get("after")
        if not after:
            return out


def reset(hs):
    for obj in ("deals", "contacts", "companies"):
        ids = existing(hs, obj)
        for i in range(0, len(ids), 100):
            hs.call("POST", f"/crm/v3/objects/{obj}/batch/archive", {"inputs": [{"id": x} for x in ids[i:i + 100]]})
        print(f"  archived {len(ids)} {obj}")
    for obj in ("meetings", "emails"):
        ids = [x["id"] for x in hs.all(obj, ["hs_timestamp"])]
        for i in range(0, len(ids), 100):
            hs.call("POST", f"/crm/v3/objects/{obj}/batch/archive", {"inputs": [{"id": x} for x in ids[i:i + 100]]})
        print(f"  archived {len(ids)} {obj}")
    for ev in hs.call("GET", "/marketing/v3/marketing-events", params={"limit": 100}).get("results", []):
        if str(ev.get("externalEventId", "")).startswith("account-hub-"):
            hs.call("DELETE", f"/marketing/v3/marketing-events/events/{ev['externalEventId']}",
                    params={"externalAccountId": ev["externalAccountId"]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portal", required=True, help="the TEST portal id; the run stops if the token is for any other")
    ap.add_argument("--reset", action="store_true", help="archive earlier demo records first")
    ap.add_argument("--extra", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo-extra-touches.csv"))
    a = ap.parse_args()
    hs = HubSpot(os.environ["HUBSPOT_TOKEN"])
    portal = str(hs.portal_id())
    if portal != a.portal:
        sys.exit(f"Token is for portal {portal}, not {a.portal}. Stopping: this script only writes to a test account.")
    ensure_properties(hs)
    if a.reset:
        reset(hs)
    elif existing(hs, "companies"):
        sys.exit("Demo companies already exist. Run with --reset to replace them.")

    data = generate()
    accts = {x["account_id"]: x for x in data["accounts"]}
    made = batch_create(hs, "companies", [{
        "name": x["name"], "domain": x["domain"], "account_hub_id": x["account_id"],
        "account_hub_target": "true", "account_hub_holdout": "true" if x["holdout"] == "yes" else "false",
        "account_hub_segment": x["segment"], "hs_analytics_source": TO_SOURCE[x["original_source"]],
        "account_hub_nhr_lead_date": x["nhr_lead_date"], "account_hub_hand_raiser_date": x["hand_raiser_date"],
        "account_hub_sql_date": x["sql_date"]} for x in data["accounts"]])
    company_id = {r["properties"]["account_hub_id"]: r["id"] for r in made}

    made = batch_create(hs, "contacts", [{
        "firstname": c["name"].split()[0], "lastname": c["name"].split()[1], "email": c["email"],
        "account_hub_id": c["contact_id"], "account_hub_role": c["role"]} for c in data["contacts"]])
    contact_id = {r["properties"]["account_hub_id"]: r["id"] for r in made}
    associate(hs, "contacts", "companies", [(contact_id[c["contact_id"]], company_id[c["account_id"]]) for c in data["contacts"]])

    stage = {"won": "closedwon", "lost": "closedlost", "open": "presentationscheduled"}
    made = batch_create(hs, "deals", [{
        "dealname": f"{accts[d['account_id']]['name']} deal", "amount": str(d["amount"]), "pipeline": "default",
        "dealstage": stage[d["status"]], "createdate": ms(d["created_date"], 12),
        "closedate": ms(d["close_date"] or d["created_date"], 18), "account_hub_id": d["deal_id"]} for d in data["deals"]])
    deal_id = {r["properties"]["account_hub_id"]: r["id"] for r in made}
    associate(hs, "deals", "companies", [(deal_id[d["deal_id"]], company_id[d["account_id"]]) for d in data["deals"]])

    native = [t for t in data["touches"] if t["detail"] in NATIVE]
    meetings = [t for t in native if t["detail"] == "meeting"]
    # HubSpot-defined association types: meeting->contact 200, meeting->company 188,
    # email->contact 198, email->company 186.
    batch_create(hs, "meetings", [{"hs_timestamp": ms(t["date"]), "hs_meeting_title": "Call with the buying team",
                                   "hs_meeting_outcome": "COMPLETED"} for t in meetings],
                 [[(contact_id[t["contact_id"]], 200), (company_id[t["account_id"]], 188)] for t in meetings])

    replies = [t for t in native if t["detail"] == "email reply"]
    batch_create(hs, "emails", [{"hs_timestamp": ms(t["date"]), "hs_email_direction": "INCOMING_EMAIL",
                                 "hs_email_subject": "Re: next steps", "hs_email_text": "Thanks, let's talk."} for t in replies],
                 [[(contact_id[t["contact_id"]], 198), (company_id[t["account_id"]], 186)] for t in replies])

    # Event attendance: one event per month, attendance on the touch date.
    att = [t for t in native if t["detail"] == "event attendance"]
    months = sorted({t["date"][:7] for t in att})
    for mth in months:
        ext = f"account-hub-{mth}"
        hs.call("POST", "/marketing/v3/marketing-events/events", {
            "externalEventId": ext, "externalAccountId": "account-hub-demo", "eventName": f"Customer roundtable {mth}",
            "eventOrganizer": "Demo Co", "eventType": "Webinar",
            "startDateTime": f"{mth}-01T15:00:00Z", "endDateTime": f"{mth}-28T16:00:00Z"})
        rows = [{"vid": int(contact_id[t["contact_id"]]), "interactionDateTime": ms(t["date"])} for t in att if t["date"][:7] == mth]
        for i in range(0, len(rows), 100):
            hs.call("POST", f"/marketing/v3/marketing-events/attendance/{ext}/attend/create",
                    {"inputs": rows[i:i + 100]}, params={"externalAccountId": "account-hub-demo"})
        print(f"  event {mth}: {len(rows)} attendees", flush=True)

    emails = {c["contact_id"]: c["email"] for c in data["contacts"]}
    with open(a.extra, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "contact_email", "company_domain", "channel", "kind", "detail"])
        w.writeheader()
        for t in data["touches"]:
            if t["detail"] not in NATIVE:
                w.writerow({"date": t["date"], "contact_email": emails.get(t["contact_id"], ""),
                            "company_domain": accts[t["account_id"]]["domain"], "channel": t["channel"],
                            "kind": t["kind"], "detail": t["detail"]})
    print(f"Done. Extra touches: {a.extra}")


if __name__ == "__main__":
    main()
