"""python3 -m abm <data folder> [--settings settings.json] [--out results.json]"""
import argparse
import json

from .engine import analyze
from .load import read_folder, read_settings

p = argparse.ArgumentParser(prog="abm")
p.add_argument("data")
p.add_argument("--settings")
p.add_argument("--out", default="results.json")
a = p.parse_args()
res = analyze(read_folder(a.data), read_settings(a.settings))
json.dump(res, open(a.out, "w"), indent=1, default=str)
print(f"Wrote {a.out}")
