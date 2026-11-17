"""Local record of AI drafts and how the worker reviewed them.

The platform only ever stores the final deliverable. The original AI draft,
and the comparison with what the worker actually approved, is personal
training data, so it's kept here on the worker's machine:

- data/drafts.jsonl       every draft this node sent for review
- data/corrections.jsonl  the worker's outcome for each draft (approved as-is,
                          approved with edits, or declined)
"""
import difflib
import json
from datetime import datetime
from pathlib import Path

from profile_paths import DATA_DIR
DRAFTS_PATH = DATA_DIR / "drafts.jsonl"
CORRECTIONS_PATH = DATA_DIR / "corrections.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _append_jsonl(path: Path, record: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def record_draft(task: dict, result: dict, model: str, platform: str) -> None:
    """Remember a draft this node submitted, so its outcome can be learned later."""
    _append_jsonl(DRAFTS_PATH, {
        "task_id": task["id"],
        "platform": platform,
        "title": task["title"],
        "description": task["description"],
        "ai_draft": result["draft_deliverable"],
        "ai_reason": result["reason"],
        "model": model,
        "drafted_at": datetime.now().isoformat(),
    })


def pending_drafts(platform: str) -> dict[int, dict]:
    """Drafts on this platform that the worker hasn't approved or declined yet."""
    resolved = {(r["platform"], r["task_id"]) for r in _read_jsonl(CORRECTIONS_PATH)}
    return {
        d["task_id"]: d for d in _read_jsonl(DRAFTS_PATH)
        if d["platform"] == platform and (platform, d["task_id"]) not in resolved
    }


def record_outcome(draft: dict, outcome: dict) -> dict:
    """Store how the worker handled a draft. Returns the saved record."""
    final = outcome.get("final_output") or ""
    similarity = difflib.SequenceMatcher(None, draft["ai_draft"], final).ratio() if final else 0.0
    record = {
        "task_id": draft["task_id"],
        "platform": draft["platform"],
        "title": draft["title"],
        "description": draft["description"],
        "outcome": outcome["status"],               # APPROVED or DECLINED
        "ai_draft": draft["ai_draft"],
        "final_output": final,
        "edited": outcome["status"] == "APPROVED" and final.strip() != draft["ai_draft"].strip(),
        "similarity": round(similarity, 3),          # 1.0 = approved unchanged
        "model": draft["model"],
        "reviewed_at": datetime.now().isoformat(),
    }
    _append_jsonl(CORRECTIONS_PATH, record)
    return record


def discard_draft(draft: dict, reason: str) -> None:
    """Stop tracking a draft whose outcome can't be trusted (e.g. task id reused)."""
    _append_jsonl(CORRECTIONS_PATH, {
        "task_id": draft["task_id"], "platform": draft["platform"],
        "title": draft["title"], "description": draft["description"],
        "outcome": "DISCARDED", "reason": reason, "reviewed_at": datetime.now().isoformat(),
    })
