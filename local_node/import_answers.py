"""Turn a returned questionnaire file into a VAI profile on this machine.

    python local_node/import_answers.py vai-answers-alice.json --profile alice

This writes local_node/profiles/alice/ with the same files the interactive
interviews produce (interview_transcript.json, deep_interview.json) and builds
voiceprint.json with the local Ollama model. Nothing is sent anywhere: the
marketplace only receives the public card when you start that profile's node:

    $env:VAI_PROFILE = "alice"; python local_node/worker_agent.py

The answers file is untrusted input: only known question keys are read, the
question text always comes from this codebase, and answers are length-capped.
"""
import argparse
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

MAX_FILE_BYTES = 2_000_000
MAX_ANSWER_CHARS = 8000
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = _CONTROL_CHARS.sub("", value).strip()[:MAX_ANSWER_CHARS]
    return value or None


def read_answers(path: Path, fmt: str, version: int) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"[Error] {path} isn't a file.")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise SystemExit(f"[Error] {path} is too large to be a questionnaire file.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SystemExit(f"[Error] {path} isn't a valid answers file ({e}).")
    if not isinstance(data, dict) or data.get("format") != fmt or data.get("version") != version:
        raise SystemExit(f"[Error] {path} isn't a version-{version} VAI questionnaire file.")
    raw = data.get("answers")
    if not isinstance(raw, dict):
        raise SystemExit("[Error] The file has no answers.")
    return {k: v for k, v in ((k, clean(v)) for k, v in raw.items()) if v}


def build_transcript(answers, spec, now) -> list[dict]:
    from interviewer import INTERVIEW_QUESTIONS
    return [
        {"question": question, "answer": answers[key], "timestamp": now, "source": "questionnaire"}
        for key, question in zip(spec.PROFILE_KEYS, INTERVIEW_QUESTIONS) if answers.get(key)
    ]


def build_deep_state(answers, spec, now) -> dict:
    """Same structure deep_interview.py writes, so its menu and notes pick it up."""
    state = {"version": 1, "entries": [], "cases": [], "notes_done": []}
    domain = answers.get(spec.AREA_KEY)
    if not domain:
        return state
    domain = domain.splitlines()[0][:100]

    def add(module, item, question, answer, case_id=None):
        state["entries"].append({"module": module, "domain": domain, "case_id": case_id, "item": item,
                                 "question": question.format(domain=domain), "answer": answer,
                                 "timestamp": now, "source": "questionnaire"})

    # Knowledge audit: record every item (blank = skipped) so it counts as complete.
    if any(answers.get(k) for k in spec.AUDIT_KEYS):
        for key, (item, template) in spec.AUDIT_KEYS.items():
            add("knowledge_audit", item, template, answers.get(key))

    if answers.get("case_story"):
        case_id = f"case-{uuid.uuid4().hex[:8]}"
        state["cases"].append({
            "id": case_id, "module": "critical_decision", "domain": domain, "status": "done",
            "questions": [[item, t.format(domain=domain)] for item, t in spec.CASE_QUESTIONS],
            "probes_ready": True, "created": now,
        })
        for key, (item, template) in spec.CASE_KEYS.items():
            add("critical_decision", item, template, answers.get(key), case_id)

    if answers.get(spec.WALK_TASK_KEY):
        case_id = f"walk-{uuid.uuid4().hex[:8]}"
        state["cases"].append({
            "id": case_id, "module": "walkthrough", "domain": domain, "status": "done",
            "sample_task": answers[spec.WALK_TASK_KEY],
            "questions": [[item, text] for item, text in spec.WALK_KEYS.values()], "created": now,
        })
        for key, (item, text) in spec.WALK_KEYS.items():
            add("walkthrough", item, text, answers.get(key), case_id)
    return state


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a returned VAI questionnaire into a local profile.")
    parser.add_argument("answers_file", type=Path)
    parser.add_argument("--profile", required=True, help="Profile folder name, e.g. alice (lowercase).")
    parser.add_argument("--force", action="store_true",
                        help="Replace an existing profile's answers (the old files are backed up first).")
    parser.add_argument("--no-voiceprint", action="store_true",
                        help="Don't build voiceprint.json now (run interviewer.py for this profile later).")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    # The profile must be chosen before the node modules work out their file paths.
    os.environ["VAI_PROFILE"] = args.profile.strip().lower()
    os.environ.pop("VAI_DATA_DIR", None)
    import profile_paths
    import questionnaire_spec as spec

    answers = read_answers(args.answers_file, spec.FORMAT, spec.VERSION)
    unknown = sorted(set(answers) - spec.ALL_KEYS)
    answers = {k: v for k, v in answers.items() if k in spec.ALL_KEYS}
    if not any(answers.get(k) for k in spec.PROFILE_KEYS):
        raise SystemExit("[Error] None of the profile questions were answered, so there's no VAI to build.")

    transcript_path = profile_paths.DATA_DIR / "interview_transcript.json"
    deep_path = profile_paths.DATA_DIR / "deep_interview.json"
    voiceprint_path = profile_paths.VOICEPRINT_PATH
    existing = [p for p in (transcript_path, deep_path, voiceprint_path) if p.exists()]
    if existing and not args.force:
        raise SystemExit(f"[Error] Profile '{profile_paths.PROFILE}' already has data in {profile_paths.PROFILE_DIR}. "
                         "Use --force to replace it (old files are backed up).")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for p in existing:
        backup = profile_paths.DATA_DIR / "backups" / f"{p.stem}.{stamp}{p.suffix}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, backup)

    now = datetime.now().isoformat(timespec="seconds")
    transcript = build_transcript(answers, spec, now)
    deep_state = build_deep_state(answers, spec, now)
    write_json(transcript_path, transcript)
    write_json(deep_path, deep_state)
    (profile_paths.DATA_DIR / "knowledge").mkdir(parents=True, exist_ok=True)

    print(f"Imported into {profile_paths.PROFILE_DIR}")
    print(f"  Profile answers: {len(transcript)} of {len(spec.PROFILE_KEYS)}")
    deep_answered = sum(1 for e in deep_state["entries"] if e["answer"])
    area = deep_state["entries"][0]["domain"] if deep_state["entries"] else None
    print(f"  Deeper answers: {deep_answered}" + (f" (area: {area})" if area else ""))
    if unknown:
        print(f"  Ignored {len(unknown)} unrecognised field(s).")

    if args.no_voiceprint:
        print("\nSkipped building voiceprint.json. Later, run:")
    else:
        import interviewer
        if interviewer.check_ollama_ready(interviewer.MODEL_NAME):
            try:
                voiceprint = interviewer.synthesize_voiceprint(transcript, interviewer.MODEL_NAME)
                write_json(voiceprint_path, voiceprint)
                profile = voiceprint.get("worker_profile", {})
                print(f"\nBuilt {voiceprint_path}")
                print(f"  {profile.get('display_name')} | {profile.get('headline')}")
                print(f"  Areas: {'; '.join(profile.get('primary_domains') or [])}")
                print("Review that file: its name, headline, summary, areas and boundaries are what the "
                      "marketplace will show.")
            except Exception as e:
                print(f"\n[Error] Couldn't build voiceprint.json ({e}). The answers are saved; to retry, run:")
                voiceprint = None
        else:
            voiceprint = None
        if voiceprint is None:
            print("To build it later, run:")
    if args.no_voiceprint or not voiceprint_path.exists():
        print(f'  $env:VAI_PROFILE = "{profile_paths.PROFILE}"; python local_node/interviewer.py')

    print("\nNext steps (PowerShell):")
    if deep_state["entries"]:
        print(f'  Optional, condense notes:  $env:VAI_PROFILE = "{profile_paths.PROFILE}"; python local_node/deep_interview.py')
    print(f'  Put this VAI online:       $env:VAI_PROFILE = "{profile_paths.PROFILE}"; python local_node/worker_agent.py')
    print(f"\nThe answers now live in {profile_paths.PROFILE_DIR}. You can delete {args.answers_file} "
          "and the email attachment once you've checked the import.")


if __name__ == "__main__":
    main()
