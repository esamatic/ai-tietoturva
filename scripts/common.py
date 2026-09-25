"""Shared helpers for the matrix scripts."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOTS = ROOT / "snapshots"
OUT = ROOT / "out"

STATUS_LABELS = {"y": "✓ Kyllä", "p": "◐ Osittain", "n": "✕ Ei", "u": "? Ei tiedossa"}
SOURCE_TYPES = {"primary", "secondary"}
TIERS = {"threshold", "differentiator"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,60}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SPAN_COL = "*"


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def save(name: str, obj) -> None:
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_all() -> dict:
    return {
        "meta": load("meta.json"),
        "structure": load("structure.json"),
        "sources": load("sources.json"),
        "cells": load("cells.json"),
        "changelog": load("changelog.json"),
    }


def key(row: str, col: str) -> str:
    return f"{row}|{col}"


def normalize_url(url: str) -> str:
    """Scheme+host+path without query, fragment or trailing slash; used to detect duplicate sources."""
    p = urlsplit(url.strip())
    return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}"


def source_id_for(url: str) -> str:
    p = urlsplit(url)
    host = p.netloc.lower().removeprefix("www.").split(".")[0]
    digest = hashlib.sha1(normalize_url(url).encode()).hexdigest()[:6]
    return f"{host}-{digest}"


def out_path(name: str) -> pathlib.Path:
    OUT.mkdir(exist_ok=True)
    return OUT / name


def set_output(name: str, value: str) -> None:
    """Write a GitHub Actions step output (no-op locally)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"[output] {name}={value}")


def gh(*args: str, input_text: str | None = None) -> str:
    """Run the GitHub CLI. With DRY_RUN=1 only prints the command."""
    if os.environ.get("DRY_RUN") == "1":
        print("[dry-run] gh", " ".join(args))
        return ""
    res = subprocess.run(["gh", *args], input=input_text, capture_output=True, text=True, check=True)
    return res.stdout


def site_url() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo:
        return ""
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"
