"""Account Hub command line.

  python3 -m accounthub run --folder data/            # the Sheet template's tabs as CSVs
  python3 -m accounthub run --hubspot [--extra x.csv] # read HubSpot (after `connect`, or HUBSPOT_TOKEN)
  python3 -m accounthub connect                       # Connect HubSpot: sign in and click Allow
Options: --settings settings.json  --out results.json  --csv results/ (tabs for the Sheet)
"""
import argparse
import json
import os
import sys

from .engine import analyze
from .export import write_csv
from .load import add_extra_touches, read_csv, read_folder, read_settings


def main():
    p = argparse.ArgumentParser(prog="accounthub")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--folder")
    r.add_argument("--hubspot", action="store_true")
    r.add_argument("--extra", help="extra touches CSV (date, contact_email, company_domain, channel, kind, detail)")
    r.add_argument("--settings")
    r.add_argument("--out", default="results.json")
    r.add_argument("--csv", help="also write the results as CSVs for the Sheet's results tabs")
    sub.add_parser("connect")
    a = p.parse_args()

    if a.cmd == "connect":
        from .connect import connect
        connect()
        return
    settings = read_settings(a.settings)
    if a.hubspot:
        from .connect import token
        from .hubspot import read
        tables = read(token(), settings)
    elif a.folder:
        tables = read_folder(a.folder)
    else:
        sys.exit("Give --folder or --hubspot.")
    if a.extra:
        missed = add_extra_touches(tables, read_csv(a.extra))
        if missed:
            print(f"{missed} extra touches matched no account (by email or domain) and were skipped.")
    res = analyze(tables, settings)
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"Wrote {a.out}")
    if a.csv:
        write_csv(res, a.csv)
        print(f"Wrote the results tabs to {a.csv}/")


if __name__ == "__main__":
    main()
