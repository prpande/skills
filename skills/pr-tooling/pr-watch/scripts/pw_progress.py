"""The fields of a PR's progress file and their starting values."""
from __future__ import annotations

import copy

COMMON_START = {"posted_reply_ids": [], "settled_ids": [], "escalated_ids": [],
                "handled_top_level_ids": {}, "slack_ts": None}
AUTHORED_START = {"slack_root_checked": False, "ci_reruns": [], "ci_rerun_queued": [], "ci_handled": [], "ci_log_retries": [],
                  "ci_log_occurrence": None, "cap_notified_head": None, "ci_fix_pushes": 0,
                  "review_fix_pushes": 0, "last_pushed_head": None, "queued_head": None,
                  "queued_at": None, "wait_notice_at": None, "retry_after": None,
                  "skip_reason": None}
REVIEWED_START = {"finding_verdicts": {}, "rereviewed_head": None, "retry_after": None}
FIELDS = frozenset({*COMMON_START, *AUTHORED_START, *REVIEWED_START})


def starting_progress(role: str | None) -> dict:
    start = dict(COMMON_START, **(AUTHORED_START if role == "authored" else REVIEWED_START))
    return copy.deepcopy(start)
