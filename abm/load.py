"""Read the four tables from a folder of CSVs (the Sheet template's tabs, downloaded or synced)."""
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


def merge(*sources):
    """HubSpot plus extra touches (e.g. ad clicks HubSpot doesn't hold) from the Sheet."""
    out = {t: [] for t in TABLES}
    for src in sources:
        for t in TABLES:
            out[t].extend(src.get(t, []))
    return out


def read_settings(path):
    return json.load(open(path)) if path and os.path.exists(path) else {}
