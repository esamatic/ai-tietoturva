"""Reset the page history to a clean baseline.

Clears cell histories and the changelog, and sets every row, column and cell
change date to the baseline date, so the page shows no "Muuttunut"/"Uusi"
badges or "Seurannassa alkaen" notes. Cell contents, sources and their
access dates are kept. Git history and source snapshots are not touched.

Usage: reset_history.py [--date YYYY-MM-DD]   (default: today)
"""
from __future__ import annotations

import argparse
import sys

from common import DATE_RE, load_all, save, today


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today())
    args = ap.parse_args()
    if not DATE_RE.match(args.date):
        print("Päivä muodossa VVVV-KK-PP.", file=sys.stderr)
        return 1
    base = args.date
    d = load_all()
    st = d["structure"]
    for item in st["rows"] + st["columns"]:
        item["added"] = base
    n_hist = 0
    for c in d["cells"].values():
        n_hist += len(c.get("history", []))
        c["history"] = []
        c["changed"] = base
        c["verified"] = min(c.get("verified", base), base)
    d["changelog"] = [{"date": base, "ref": "", "changes": [],
                       "summary": "Lähtötilanne. Muutoksia seurataan tästä päivästä alkaen."}]
    for name in ("structure", "cells", "changelog"):
        save(f"{name}.json", d[name])
    print(f"Historia nollattu päivään {base}: {len(d['cells'])} solua, {n_hist} historiamerkintää poistettu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
