"""Where a VAI's private files live on this machine.

One machine can hold several VAI profiles (yours, plus test VAIs built from
colleagues' questionnaire answers). Each profile is a folder that never leaves
this machine:

    local_node/profiles/<name>/voiceprint.json        the voiceprint
    local_node/profiles/<name>/data/                  interview answers, notes,
                                                      memory, reviewed drafts
    local_node/profiles/<name>/node_credentials.json  marketplace access tokens

Pick a profile with the VAI_PROFILE environment variable, e.g. in PowerShell:
    $env:VAI_PROFILE = "alice"; python local_node/worker_agent.py

Without VAI_PROFILE, the original single-profile layout is used
(local_node/voiceprint.json and local_node/data/), so existing data keeps working.
VAI_DATA_DIR still overrides the data folder (handy for tests).
"""
import os
import re
from pathlib import Path

NODE_DIR = Path(__file__).resolve().parent
PROFILES_DIR = Path(os.getenv("VAI_PROFILES_DIR") or NODE_DIR / "profiles")
PROFILE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def valid_profile_name(name: str) -> bool:
    return bool(PROFILE_NAME_PATTERN.match(name or ""))


PROFILE = (os.getenv("VAI_PROFILE") or "").strip().lower() or None
if PROFILE is not None and not valid_profile_name(PROFILE):
    raise SystemExit(f"[Error] VAI_PROFILE '{PROFILE}' must be lowercase letters, numbers, '-' or '_'.")

if PROFILE:
    PROFILE_DIR = PROFILES_DIR / PROFILE
    VOICEPRINT_PATH = PROFILE_DIR / "voiceprint.json"
    _default_data = PROFILE_DIR / "data"
else:
    PROFILE_DIR = NODE_DIR
    VOICEPRINT_PATH = NODE_DIR / "voiceprint.json"
    _default_data = NODE_DIR / "data"

DATA_DIR = Path(os.getenv("VAI_DATA_DIR") or _default_data)
CREDENTIALS_PATH = PROFILE_DIR / "node_credentials.json"


def describe() -> str:
    return f"profile '{PROFILE}'" if PROFILE else "default profile"
