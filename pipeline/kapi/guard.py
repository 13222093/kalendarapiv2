"""Refuses to compute anything inside a pre-registered period before the plan is registered.

The plan (PREREGISTRATION.md) is registered when the GitHub Release `prereg-v1` exists. Write its repository into
pipeline/REGISTRATION.json as {"repo": "owner/name", "tag": "prereg-v1"}. The guard then asks GitHub whether that
Release is published (not a draft) before it lets any registered period through.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import urllib.request

# Every 2019 day is used by the plan: Q1 and H4 (Aug to Oct), H2 targets (Aug to Oct) and donor masks (all of 2019),
# and the wet-season placebo (Jan to Mar).
REGISTERED_WINDOWS = [
    (dt.date(2019, 1, 1), dt.date(2019, 12, 31), "PREREGISTRATION.md: Q1, H2, H4 and the placebo use 2019"),
]
REG_FILE = pathlib.Path(__file__).resolve().parents[1] / "REGISTRATION.json"


class NotRegisteredError(RuntimeError):
    pass


def _fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "kalenderapi-pipeline/0.1",
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception:
        return None


def registered_release(reg_file: pathlib.Path = REG_FILE, fetch=_fetch) -> dict | None:
    """The published Release named in REGISTRATION.json, or None."""
    if not reg_file.exists():
        return None
    info = json.loads(reg_file.read_text(encoding="utf-8"))
    repo, tag = info.get("repo"), info.get("tag", "prereg-v1")
    if not repo:
        return None
    data = fetch(f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    if not data or data.get("draft") or not data.get("published_at"):
        return None
    return {"repo": repo, "tag": tag, "published_at": data["published_at"], "url": data.get("html_url")}


def overlapping(start: dt.date, end: dt.date) -> list[tuple]:
    return [w for w in REGISTERED_WINDOWS if start <= w[1] and end >= w[0]]


def check(start: dt.date, end: dt.date, reg_file: pathlib.Path = REG_FILE, fetch=_fetch) -> dict | None:
    """None if the period is outside every registered window; the Release if it is registered; otherwise raise."""
    hits = overlapping(start, end)
    if not hits:
        return None
    rel = registered_release(reg_file, fetch)
    if rel is None:
        why = "; ".join(w[2] for w in hits)
        raise NotRegisteredError(
            f"{start} to {end} is inside a pre-registered period ({why}). Publish the GitHub Release prereg-v1 "
            f"and write {reg_file.name} first.")
    return rel
