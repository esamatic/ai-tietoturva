"""Validate a patch and apply it to data/*.json.

Usage:
  apply_patch.py --event $GITHUB_EVENT_PATH   # patch inside an issue comment
  apply_patch.py --patch-file out/patch.json --ref "#12"

Nothing is written unless the whole patch validates. Outputs:
  out/pr_body.md on success, out/error.md on failure, step output ok=true/false.
The comment text is only ever parsed as JSON; it is never executed.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys

from common import (DATE_RE, ID_RE, SOURCE_TYPES, SPAN_COL, STATUS_LABELS, TIERS, key, load_all,
                    normalize_url, out_path, save, set_output, source_id_for, today)

PATCH_RE = re.compile(r"BEGIN-PATCH\s*(.*?)\s*END-PATCH", re.S)
MAX_TEXT = 500


class PatchError(Exception):
    pass


def extract_patch(text: str) -> dict:
    m = PATCH_RE.search(text)
    if not m:
        raise PatchError(["Kommentista ei löytynyt BEGIN-PATCH ... END-PATCH -lohkoa."])
    body = "\n".join(l for l in m.group(1).splitlines() if not re.match(r"^\s*(```|~~~)", l))
    try:
        patch = json.loads(body)
    except json.JSONDecodeError as e:
        raise PatchError([f"Patch ei ole kelvollista JSON:ia: {e}"])
    if not isinstance(patch, dict):
        raise PatchError(["Patchin pitää olla JSON-objekti."])
    return patch


def apply(patch: dict, data: dict, ref: str) -> tuple[dict, list[str], list[dict]]:
    """Returns (new_data, errors, changes). data is not mutated."""
    d = copy.deepcopy(data)
    st, cells, sources = d["structure"], d["cells"], d["sources"]
    errors: list[str] = []
    changes: list[dict] = []
    now = today()

    allowed = {"summary", "sources", "columns", "rows", "cells", "unchanged"}
    for k in set(patch) - allowed:
        errors.append(f"Tuntematon kenttä patchissa: {k}")
    summary = patch.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("Kenttä summary puuttuu tai on tyhjä.")

    # --- sources -------------------------------------------------------
    by_norm = {normalize_url(s["url"]): s for s in sources}
    ids = {s["id"] for s in sources}
    alias: dict[str, str] = {}  # id given in patch -> actual id

    def register(src: dict, where: str, default_vendor: str = "") -> str | None:
        url = src.get("url", "")
        if not isinstance(url, str) or not re.match(r"^https?://", url):
            errors.append(f"{where}: url puuttuu tai ei ole http(s).")
            return None
        existing = by_norm.get(normalize_url(url))
        if existing:
            if src.get("id"):
                alias[src["id"]] = existing["id"]
            return existing["id"]
        stype = src.get("type", "primary")
        if stype not in SOURCE_TYPES:
            errors.append(f"{where}: type pitää olla primary tai secondary.")
            return None
        sid = src.get("id") or source_id_for(url)
        if not ID_RE.match(sid) or sid in ids:
            sid = source_id_for(url)
        new = {"id": sid, "vendor": src.get("vendor") or default_vendor, "title": (src.get("title") or url)[:200],
               "url": url, "type": stype, "monitor": bool(src.get("monitor", stype == "primary")),
               "selector": src.get("selector", "")}
        sources.append(new)
        ids.add(sid)
        by_norm[normalize_url(url)] = new
        if src.get("id"):
            alias[src["id"]] = sid
        changes.append({"kind": "source", "key": sid, "text": new["title"]})
        return sid

    for i, src in enumerate(patch.get("sources", []) or []):
        if not isinstance(src, dict):
            errors.append(f"sources[{i}] ei ole objekti.")
            continue
        register(src, f"sources[{i}]")

    # --- columns -------------------------------------------------------
    vendor_ids = {v["id"] for v in st["vendors"]}
    col_ids = {c["id"] for c in st["columns"]}
    for i, col in enumerate(patch.get("columns", []) or []):
        where = f"columns[{i}]"
        cid, vendor = col.get("id", ""), col.get("vendor", "")
        if not ID_RE.match(cid or ""):
            errors.append(f"{where}: id puuttuu tai on virheellinen (a-z, 0-9, _ tai -).")
            continue
        if cid in col_ids:
            errors.append(f"{where}: sarake {cid} on jo olemassa.")
            continue
        if vendor not in vendor_ids:
            if col.get("vendor_name") and ID_RE.match(vendor or ""):
                st["vendors"].append({"id": vendor, "name": col["vendor_name"]})
                vendor_ids.add(vendor)
            else:
                errors.append(f"{where}: tuntematon vendor {vendor!r} (uudelle anna myös vendor_name).")
                continue
        if not col.get("plan"):
            errors.append(f"{where}: plan puuttuu.")
            continue
        new = {"id": cid, "vendor": vendor, "plan": col["plan"], "meta": col.get("meta", ""), "added": now}
        # keep vendor columns together
        last = max((j for j, c in enumerate(st["columns"]) if c["vendor"] == vendor), default=len(st["columns"]) - 1)
        st["columns"].insert(last + 1, new)
        col_ids.add(cid)
        changes.append({"kind": "column", "key": cid, "text": col["plan"]})

    # --- rows ----------------------------------------------------------
    group_ids = {g["id"] for g in st["groups"]}
    row_by_id = {r["id"]: r for r in st["rows"]}
    for i, row in enumerate(patch.get("rows", []) or []):
        where = f"rows[{i}]"
        rid, group = row.get("id", ""), row.get("group", "")
        if not ID_RE.match(rid or ""):
            errors.append(f"{where}: id puuttuu tai on virheellinen.")
            continue
        if rid in row_by_id:
            errors.append(f"{where}: rivi {rid} on jo olemassa.")
            continue
        if not row.get("label"):
            errors.append(f"{where}: label puuttuu.")
            continue
        if group not in group_ids:
            if row.get("group_label") and ID_RE.match(group or ""):
                tier = row.get("group_tier", "differentiator")
                if tier not in TIERS:
                    errors.append(f"{where}: group_tier pitää olla threshold tai differentiator.")
                    continue
                st["groups"].append({"id": group, "label": row["group_label"], "tier": tier})
                group_ids.add(group)
            else:
                errors.append(f"{where}: tuntematon group {group!r} (uudelle anna myös group_label).")
                continue
        new = {"id": rid, "group": group, "label": row["label"], "hint": row.get("hint", ""), "added": now}
        if row.get("span"):
            new["span"] = True
        last = max((j for j, r in enumerate(st["rows"]) if r["group"] == group), default=len(st["rows"]) - 1)
        st["rows"].insert(last + 1, new)
        row_by_id[rid] = new
        changes.append({"kind": "row", "key": rid, "text": row["label"]})

    # --- cells ---------------------------------------------------------
    col_vendor = {c["id"]: c["vendor"] for c in st["columns"]}
    seen = set()
    for i, c in enumerate(patch.get("cells", []) or []):
        where = f"cells[{i}]"
        if not isinstance(c, dict):
            errors.append(f"{where} ei ole objekti.")
            continue
        rid, cid = c.get("row"), c.get("col")
        row = row_by_id.get(rid)
        if row is None:
            errors.append(f"{where}: tuntematon rivi {rid!r}. Jos rivi lisättiin juuri, yhdistä ensin sen pull request.")
            continue
        if row.get("span"):
            if cid != SPAN_COL:
                errors.append(f"{where}: rivi {rid} on koko leveyden rivi, col pitää olla \"*\".")
                continue
        elif cid not in col_ids:
            errors.append(f"{where}: tuntematon sarake {cid!r}.")
            continue
        k = key(rid, cid)
        if k in seen:
            errors.append(f"{where}: solu {k} esiintyy patchissa useasti.")
            continue
        seen.add(k)
        status, text = c.get("status"), (c.get("text") or "").strip()
        if status not in STATUS_LABELS:
            errors.append(f"{where}: status pitää olla y, p, n tai u.")
            continue
        if not text or len(text) > MAX_TEXT:
            errors.append(f"{where}: text puuttuu tai on yli {MAX_TEXT} merkkiä.")
            continue
        cell_sources = []
        for j, s in enumerate(c.get("sources", []) or []):
            sw = f"{where}.sources[{j}]"
            if not isinstance(s, dict):
                errors.append(f"{sw} ei ole objekti.")
                continue
            sid = s.get("id")
            sid = alias.get(sid, sid)
            if sid and sid in ids:
                pass
            elif s.get("url"):
                sid = register(s, sw, col_vendor.get(cid, ""))
                if sid is None:
                    continue
            else:
                errors.append(f"{sw}: tuntematon lähde {s.get('id')!r} eikä url:ia annettu.")
                continue
            accessed = s.get("accessed", now)
            if not DATE_RE.match(str(accessed)):
                errors.append(f"{sw}: accessed pitää olla muodossa VVVV-KK-PP.")
                continue
            entry = {"id": sid, "accessed": accessed}
            if s.get("note"):
                entry["note"] = str(s["note"])[:200]
            cell_sources.append(entry)
        if status != "u" and not cell_sources:
            errors.append(f"{where}: tilalla {status} pitää olla vähintään yksi lähde.")
            continue

        old = cells.get(k)
        new = {"status": status, "text": text, "sources": cell_sources, "verified": now,
               "changed": now, "history": []}
        if c.get("verify"):
            new["verify"] = True
        if old is None:
            cells[k] = new
            changes.append({"kind": "new", "key": k, "to": status, "text": text, "reason": c.get("reason", "")})
            continue
        substantive = old["status"] != status or old["text"] != text
        if substantive and not (c.get("reason") or "").strip():
            errors.append(f"{where}: muutetulle solulle {k} pitää antaa reason.")
            continue
        if substantive:
            hist = {k2: old[k2] for k2 in ("status", "text", "sources") if k2 in old}
            if old.get("verify"):
                hist["verify"] = True
            hist.update({"from": old.get("changed", ""), "until": now, "reason": c["reason"].strip()})
            new["history"] = [hist] + old.get("history", [])
            changes.append({"kind": "status" if old["status"] != status else "text", "key": k,
                            "from": old["status"], "to": status, "text": text, "reason": c["reason"].strip()})
        else:
            new["changed"] = old.get("changed", now)
            new["history"] = old.get("history", [])
            changes.append({"kind": "sources", "key": k, "to": status, "text": "lähteet päivitetty"})
        cells[k] = new

    for k in patch.get("unchanged", []) or []:
        if k in seen:
            continue
        if k not in cells:
            errors.append(f"unchanged: solua {k!r} ei ole olemassa.")
            continue
        cells[k]["verified"] = now

    if not errors and not changes and not patch.get("unchanged"):
        errors.append("Patch ei sisällä muutoksia eikä unchanged-listaa.")

    if not errors:
        d["cells"] = dict(sorted(cells.items()))
        d["changelog"].insert(0, {"date": now, "ref": ref, "summary": (summary or "").strip(),
                                  "changes": [ch for ch in changes if ch["kind"] != "sources"]})
    return d, errors, changes


def labels(data: dict) -> tuple[dict, dict]:
    st = data["structure"]
    vendors = {v["id"]: v["name"] for v in st["vendors"]}
    rows = {r["id"]: r["label"] for r in st["rows"]}
    cols = {c["id"]: f'{vendors.get(c["vendor"], c["vendor"])} {c["plan"]}' for c in st["columns"]}
    cols[SPAN_COL] = "kaikki"
    return rows, cols


def pr_body(patch: dict, changes: list[dict], data: dict, ref: str) -> str:
    rows, cols = labels(data)
    lines = [f"**{patch['summary'].strip()}**", ""]
    if ref:
        lines += [f"Lähtöisin: {ref}", ""]
    cell_changes = [c for c in changes if c["kind"] in {"status", "text", "new", "sources"}]
    if cell_changes:
        lines += ["| Solu | Muutos | Uusi teksti | Syy |", "|---|---|---|---|"]
        for c in cell_changes:
            r, col = c["key"].split("|", 1)
            if c["kind"] == "status":
                what = f'{STATUS_LABELS[c["from"]]} → {STATUS_LABELS[c["to"]]}'
            elif c["kind"] == "new":
                what = f'uusi: {STATUS_LABELS[c["to"]]}'
            elif c["kind"] == "text":
                what = "teksti"
            else:
                what = "lähteet"
            cell = f'{rows.get(r, r)} / {cols.get(col, col)}'
            txt = c.get("text", "").replace("|", "\\|")
            reason = c.get("reason", "").replace("|", "\\|")
            lines.append(f"| {cell} | {what} | {txt} | {reason} |")
        lines.append("")
    for kind, title in (("row", "Uudet rivit"), ("column", "Uudet sarakkeet"), ("source", "Uudet lähteet")):
        items = [c for c in changes if c["kind"] == kind]
        if items:
            lines += [f"**{title}:** " + ", ".join(f'`{c["key"]}` ({c["text"]})' for c in items), ""]
    n_unchanged = len(patch.get("unchanged", []) or [])
    if n_unchanged:
        lines.append(f"Tarkistettu ennallaan: {n_unchanged} solua.")
    lines += ["", "Tarkista muutokset ja lähteet ennen yhdistämistä."]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event")
    ap.add_argument("--patch-file")
    ap.add_argument("--ref", default="")
    args = ap.parse_args()

    ref = args.ref
    try:
        if args.event:
            event = json.load(open(args.event, encoding="utf-8"))
            ref = ref or f'#{event["issue"]["number"]}'
            patch = extract_patch(event["comment"]["body"])
        elif args.patch_file:
            patch = json.load(open(args.patch_file, encoding="utf-8"))
        else:
            ap.error("anna --event tai --patch-file")
        data = load_all()
        new_data, errors, changes = apply(patch, data, ref)
        if errors:
            raise PatchError(errors)
    except PatchError as e:
        msg = "\n".join(f"- {x}" for x in e.args[0])
        out_path("error.md").write_text(
            "Patchia ei otettu käyttöön, koska validointi epäonnistui:\n\n" + msg +
            "\n\nPyydä Claudelta korjattu versio ja liitä se uutena kommenttina.", encoding="utf-8")
        print(msg, file=sys.stderr)
        set_output("ok", "false")
        return 0  # the workflow reports the error as a comment

    for name in ("structure", "sources", "cells", "changelog"):
        save(f"{name}.json", new_data[name])
    out_path("pr_body.md").write_text(pr_body(patch, changes, new_data, ref), encoding="utf-8")
    set_output("ok", "true")
    print(f"Sovellettu: {len(changes)} muutosta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
