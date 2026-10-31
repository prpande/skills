"""Shared PR keys, state paths and timestamp helpers for pr-watch."""
from __future__ import annotations

import datetime
import os
import pathlib
import re

NAME = re.compile(r"^[A-Za-z0-9_.-]+$")

REF = re.compile(r"^([^/#\s]+)/([^/#\s]+)#(\d+)$")
URL = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)/?$")
BARE = re.compile(r"^\d+$")


def home() -> pathlib.Path:
    override = os.environ.get("PR_WATCH_HOME")
    return pathlib.Path(override) if override else pathlib.Path.home() / ".claude" / "pr-watch"


def parse_ref(ref: str, default_repo: str | None = None) -> tuple[str, str, int]:
    ref = ref.strip()
    if BARE.match(ref):
        match = REF.match(f"{default_repo or ''}#{ref}")
    else:
        match = REF.match(ref) or URL.match(ref)
    if not match:
        raise ValueError(f"not a PR reference: {ref!r}")
    owner, repo, number = match.group(1).lower(), match.group(2).lower(), int(match.group(3))
    for name in (owner, repo):
        if not NAME.match(name) or name in (".", ".."):
            raise ValueError(f"invalid owner or repo name in {ref!r}")
    return owner, repo, number


def repo_slug(owner: str, repo: str) -> str:
    return f"{owner}/{repo}".lower()


def pr_key(owner: str, repo: str, n: int) -> str:
    return f"{repo_slug(owner, repo)}#{n}"


def sessions_root() -> pathlib.Path:
    return home() / "sessions"


def session_dir(session_id: str) -> pathlib.Path:
    if not NAME.match(session_id) or session_id in (".", ".."):
        raise ValueError(f"invalid session id: {session_id!r}")
    return sessions_root() / session_id


def pr_dir(owner: str, repo: str) -> pathlib.Path:
    return home() / "prs" / owner.lower() / repo.lower()


def lease_path(owner: str, repo: str, n: int) -> pathlib.Path:
    return pr_dir(owner, repo) / f"{n}.json"


def progress_path(owner: str, repo: str, n: int) -> pathlib.Path:
    return pr_dir(owner, repo) / f"{n}.progress.json"


def claim_lock_path(owner: str, repo: str, n: int) -> pathlib.Path:
    return pr_dir(owner, repo) / f"{n}.claim.lock"


def push_lock_path(owner: str, repo: str) -> pathlib.Path:
    return pr_dir(owner, repo) / "push.lock"


def iso_utc(epoch: float) -> str:
    moment = datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> float:
    moment = datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
    return moment.replace(tzinfo=datetime.timezone.utc).timestamp()
