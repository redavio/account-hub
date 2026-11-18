"""Read HubSpot into Account Hub's four tables. Read only.

Needs an access token: from Connect HubSpot (OAuth), or an admin token from a HubSpot
private app. Scopes: crm.objects.companies/contacts/deals.read, crm.schemas.*.read,
sales-email-read, crm.objects.marketing_events.read.

What is read, and from where (every property name can be changed in settings["hubspot"]):
  Accounts   companies; target list, holdout and segment from company properties; original
             source from HubSpot's own "Original source" (hs_analytics_source).
  Stage dates  Non-hand-raiser lead, Hand-raiser and SQL dates from company properties
             (default: HubSpot's own date-entered-stage properties).
  Contacts   role from a contact property.
  Deals      Opportunity = deal created; Closed won = deal closed won.
  Touches    meetings and calls (sales outreach, engaged), email replies (engaged), sales
             emails sent (reached), marketing event attendance (events and webinars, engaged).
             Touches HubSpot doesn't hold through its API (web visits, ad clicks, marketing
             email sends) come from the Sheet's extra touches tab.
"""
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.hubapi.com"

SOURCE_MAP = {  # HubSpot original source -> Account Hub channel
    "ORGANIC_SEARCH": "organic search (SEO)", "PAID_SEARCH": "paid search", "EMAIL_MARKETING": "email",
    "SOCIAL_MEDIA": "organic social", "REFERRALS": "referral and partner", "OTHER_CAMPAIGNS": "other campaigns",
    "DIRECT_TRAFFIC": "direct", "OFFLINE": "sales outreach", "PAID_SOCIAL": "paid social",
    "AI_REFERRALS": "LLM answers (AEO)",
}

DEFAULT_PROPS = {
    "target": "account_hub_target",          # company: is this an ABM target? (blank property = all companies)
    "holdout": "account_hub_holdout",        # company: set aside, no ABM
    "segment": "account_hub_segment",        # company: SMB / Mid-market / Enterprise
    "role": "account_hub_role",              # contact: buying committee role
    "nhr_lead_date": "hs_v2_date_entered_lead",
    "hand_raiser_date": "hs_v2_date_entered_marketingqualifiedlead",
    "sql_date": "hs_v2_date_entered_salesqualifiedlead",
}


def _context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class HubSpot:
    def __init__(self, token):
        self.token, self.ctx = token, _context()

    def call(self, method, path, body=None, params=None):
        url = API + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(6):
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, context=self.ctx, timeout=60) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                if e.code in (429, 502, 503) and attempt < 5:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"HubSpot {method} {path}: {e.code} {e.read().decode()[:400]}") from None
        return {}

    def all(self, obj, props, associations=None):
        """Every record of an object type, following pages."""
        out, after = [], None
        while True:
            params = {"limit": 100, "properties": props, "archived": "false"}
            if associations:
                params["associations"] = associations
            if after:
                params["after"] = after
            r = self.call("GET", f"/crm/v3/objects/{obj}", params=params)
            out += r.get("results", [])
            after = r.get("paging", {}).get("next", {}).get("after")
            if not after:
                return out

    def portal_id(self):
        return self.call("GET", "/account-info/v3/details").get("portalId")


def _date(v):
    if not v:
        return ""
    if str(v).isdigit():  # epoch milliseconds
        return time.strftime("%Y-%m-%d", time.gmtime(int(v) / 1000))
    return str(v)[:10]


def _yes(v):
    return str(v).strip().lower() in ("true", "yes", "1", "y")


def _assoc(rec, kind):
    return [a["id"] for a in rec.get("associations", {}).get(kind, {}).get("results", [])]


def read(token, settings=None):
    props = {**DEFAULT_PROPS, **((settings or {}).get("hubspot") or {})}
    hs = HubSpot(token)
    companies = hs.all("companies", ["name", "domain", "hs_analytics_source", props["target"], props["holdout"],
                                     props["segment"], props["nhr_lead_date"], props["hand_raiser_date"], props["sql_date"]])
    has_target = any(c["properties"].get(props["target"]) not in (None, "") for c in companies)
    accounts = [{
        "account_id": c["id"], "name": c["properties"].get("name") or c["id"],
        "domain": c["properties"].get("domain") or "",
        "segment": c["properties"].get(props["segment"]) or "All",
        "target": "yes" if (not has_target or _yes(c["properties"].get(props["target"]))) else "no",
        "holdout": "yes" if _yes(c["properties"].get(props["holdout"])) else "no",
        "original_source": SOURCE_MAP.get(c["properties"].get("hs_analytics_source") or "", ""),
        "nhr_lead_date": _date(c["properties"].get(props["nhr_lead_date"])),
        "hand_raiser_date": _date(c["properties"].get(props["hand_raiser_date"])),
        "sql_date": _date(c["properties"].get(props["sql_date"])),
    } for c in companies]

    raw_contacts = hs.all("contacts", ["firstname", "lastname", "email", props["role"]], ["companies"])
    contacts, contact_company = [], {}
    for c in raw_contacts:
        comp = _assoc(c, "companies")
        if not comp:
            continue
        contact_company[c["id"]] = comp[0]
        p = c["properties"]
        contacts.append({"contact_id": c["id"], "account_id": comp[0], "email": p.get("email") or "",
                         "name": f"{p.get('firstname') or ''} {p.get('lastname') or ''}".strip(),
                         "role": p.get(props["role"]) or ""})

    deals = []
    for d in hs.all("deals", ["amount", "createdate", "closedate", "dealstage", "hs_is_closed_won", "hs_is_closed"], ["companies"]):
        comp = _assoc(d, "companies")
        if not comp:
            continue
        p = d["properties"]
        won = _yes(p.get("hs_is_closed_won")) or p.get("dealstage") == "closedwon"
        lost = (_yes(p.get("hs_is_closed")) and not won) or p.get("dealstage") == "closedlost"
        deals.append({"deal_id": d["id"], "account_id": comp[0], "amount": p.get("amount") or 0,
                      "created_date": _date(p.get("createdate")), "status": "won" if won else ("lost" if lost else "open"),
                      "close_date": _date(p.get("closedate")) if won else ""})

    touches = []

    def add(account, contact, day, channel, kind, detail, tid):
        if account and day:
            touches.append({"touch_id": tid, "account_id": account, "contact_id": contact or "",
                            "date": day, "channel": channel, "kind": kind, "detail": detail})

    for m in hs.all("meetings", ["hs_timestamp", "hs_meeting_outcome"], ["contacts", "companies"]):
        if (m["properties"].get("hs_meeting_outcome") or "COMPLETED") not in ("COMPLETED", ""):
            continue
        ct = _assoc(m, "contacts")
        acct = (_assoc(m, "companies") or [contact_company.get(ct[0]) if ct else None])[0]
        add(acct, ct[0] if ct else "", _date(m["properties"].get("hs_timestamp")), "sales outreach", "engaged", "meeting", "M" + m["id"])
    for c in hs.all("calls", ["hs_timestamp", "hs_call_status"], ["contacts", "companies"]):
        if (c["properties"].get("hs_call_status") or "COMPLETED") != "COMPLETED":
            continue
        ct = _assoc(c, "contacts")
        acct = (_assoc(c, "companies") or [contact_company.get(ct[0]) if ct else None])[0]
        add(acct, ct[0] if ct else "", _date(c["properties"].get("hs_timestamp")), "sales outreach", "engaged", "call", "K" + c["id"])
    for e in hs.all("emails", ["hs_timestamp", "hs_email_direction"], ["contacts", "companies"]):
        ct = _assoc(e, "contacts")
        acct = (_assoc(e, "companies") or [contact_company.get(ct[0]) if ct else None])[0]
        incoming = e["properties"].get("hs_email_direction") == "INCOMING_EMAIL"
        add(acct, ct[0] if ct else "", _date(e["properties"].get("hs_timestamp")), "sales outreach",
            "engaged" if incoming else "reached", "email reply" if incoming else "sales email sent", "E" + e["id"])

    # Marketing event attendance, by the event's own id (works for events from any app).
    events, after = [], None
    while True:
        r = hs.call("GET", "/marketing/v3/marketing-events", params={"limit": 100, **({"after": after} if after else {})})
        events += r.get("results", [])
        after = r.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
    for ev in events:
        after = None
        while True:
            params = {"limit": 100, **({"after": after} if after else {})}
            r = hs.call("GET", f"/marketing/v3/marketing-events/participations/{ev['objectId']}/breakdown", params=params)
            for row in r.get("results", []):
                if row.get("properties", {}).get("attendanceState") != "ATTENDED":
                    continue
                cid = str(row.get("associations", {}).get("contact", {}).get("contactId") or "")
                when = row.get("properties", {}).get("occurredAt") or row.get("createdAt")
                add(contact_company.get(cid), cid, _date(when), "events and webinars", "engaged", "event attendance", "V" + row["id"])
            after = r.get("paging", {}).get("next", {}).get("after")
            if not after:
                break

    return {"accounts": accounts, "contacts": contacts, "deals": deals, "touches": touches}
