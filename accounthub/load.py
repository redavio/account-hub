"""Read the four tables from a folder of CSVs (the Sheet template's tabs), and merge sources."""
import csv
import json
import os

TABLES = ["accounts", "contacts", "deals", "touches"]


def read_folder(path):
    out = {}
    for name in TABLES:
        f = os.path.join(path, f"{name}.csv")
        out[name] = list(csv.DictReader(open(f))) if os.path.exists(f) else []
    return out


def read_csv(path):
    return list(csv.DictReader(open(path)))


def add_extra_touches(tables, extra):
    """Touches HubSpot doesn't hold (web visits, ad clicks...), matched to an account by
    account_id, else contact email, else company domain. Returns how many didn't match."""
    by_email = {c.get("email", "").lower(): c for c in tables["contacts"] if c.get("email")}
    by_domain = {a.get("domain", "").lower(): a["account_id"] for a in tables["accounts"] if a.get("domain")}
    unmatched = 0
    for i, t in enumerate(extra):
        contact = by_email.get((t.get("contact_email") or "").lower())
        account = t.get("account_id") or (contact["account_id"] if contact else by_domain.get((t.get("company_domain") or "").lower()))
        if not account:
            unmatched += 1
            continue
        tables["touches"].append({"touch_id": t.get("touch_id") or f"X{i + 1}", "account_id": account,
                                  "contact_id": t.get("contact_id") or (contact["contact_id"] if contact else ""),
                                  "date": t["date"], "channel": t["channel"], "kind": t.get("kind") or "engaged",
                                  "detail": t.get("detail", "")})
    return unmatched


def read_settings(path):
    return json.load(open(path)) if path and os.path.exists(path) else {}
