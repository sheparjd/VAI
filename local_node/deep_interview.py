"""Deeper, multi-session expertise interview for the VAI voiceprint.

The basic interview (interviewer.py) captures who the worker is. This one
captures how they think, using methods from cognitive task analysis:

- Knowledge audit (after Applied Cognitive Task Analysis): what the worker
  notices, their rules of thumb, warning signs, common mistakes and quality
  standards, for each area of expertise.
- Tough case (after the Critical Decision Method): the worker tells one real,
  difficult case; the local model then asks follow-up questions about that
  specific story (cues, options, what a beginner would have done, what-ifs).
- Walkthrough (think-aloud): the local model writes a realistic sample task
  and the worker talks through how they would approach it.

Built for low fatigue: one question at a time, every answer saved
immediately, 'skip' drops a question for good, 'pause' stops and resumes later.
Everything stays on this machine (data/deep_interview.json and
data/expertise_notes.json), and is indexed into local memory by memory_store.py.

Usage:  python local_node/deep_interview.py [--no-followups]
"""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import ollama

MODEL_NAME = os.getenv("OLLAMA_MODEL", "llama3.1")
from profile_paths import DATA_DIR, VOICEPRINT_PATH
STATE_PATH = DATA_DIR / "deep_interview.json"
NOTES_PATH = DATA_DIR / "expertise_notes.json"

MODULES = {
    "knowledge_audit": "Knowledge audit",
    "critical_decision": "Tough case",
    "walkthrough": "Walkthrough",
}

KNOWLEDGE_AUDIT = [
    ("big_picture", "When you take on a {domain} task, what do you keep in mind the whole way through, "
                    "the big picture a newer person might lose track of?"),
    ("noticing", "What do you notice in {domain} work that less experienced people tend to miss? "
                 "A specific example helps."),
    ("early_signs", "Early on in a {domain} task, what tells you whether it's going to be "
                    "straightforward or tricky?"),
    ("rules_of_thumb", "What rules of thumb or shortcuts do you rely on in {domain}?"),
    ("anomalies", "How do you spot that something is off or unusual in {domain} work? "
                  "What are the warning signs?"),
    ("when_stuck", "In {domain}, when your first approach doesn't work, what do you try next?"),
    ("common_mistakes", "What are the most common mistakes people make in {domain}, "
                        "and how do you avoid them?"),
    ("quality", "How can you tell a {domain} result is done really well, rather than just acceptable?"),
]

CDM_OPENING = [
    ("story", "Think of a real, memorable situation in {domain} where your experience made the "
              "difference: a tricky problem or a tough call. Briefly tell the story."),
    ("timeline", "Now walk through the key moments in order: what happened first, and what "
                 "decisions did you make along the way?"),
]
CDM_FALLBACK_PROBES = [
    "At the key moment, what did you notice that told you what was really going on?",
    "What other options did you consider, and why didn't you take them?",
    "What would someone less experienced have done in that situation?",
    "If one important detail had been different, what would you have done instead?",
]
CDM_CLOSING = ("lesson", "Looking back, what's the lesson you'd pass on to someone newer in {domain}?")

WALKTHROUGH_QUESTIONS = [
    ("start", "How would you start on this? Talk through your first steps."),
    ("clarify", "What would you check, or ask the client, before going further?"),
    ("deliverable", "What would the finished result look like?"),
    ("risks", "Where could this go wrong, and how would you guard against it?"),
]

NOTE_CATEGORIES = {
    "rules_of_thumb": "Rules of thumb",
    "cues_to_notice": "What to notice",
    "common_mistakes": "Common mistakes to avoid",
    "quality_standards": "What 'done well' looks like",
}


class Pause(Exception):
    """The worker asked to stop for now."""


# --- Storage ---------------------------------------------------------------
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_json(path: Path, data) -> None:
    """Atomic write: a crash mid-write can't corrupt earlier answers."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_state() -> dict:
    state = {"version": 1, "entries": [], "cases": [], "notes_done": []}
    if STATE_PATH.exists():
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state.update(json.load(f))
    return state


def save_state(state: dict) -> None:
    _write_json(STATE_PATH, state)


def load_notes() -> dict:
    if not NOTES_PATH.exists():
        return {}
    with open(NOTES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def record(state: dict, **entry) -> None:
    entry["timestamp"] = _now()
    state["entries"].append(entry)
    save_state(state)


def recorded_items(state: dict, module: str, domain: str, case_id: str | None = None) -> set[str]:
    """Items already answered or skipped (so they aren't asked again)."""
    return {
        e["item"] for e in state["entries"]
        if e["module"] == module and e["domain"] == domain and e.get("case_id") == case_id
    }


# --- Talking to the worker -------------------------------------------------
def ask(question: str, optional: bool = False, confirm: bool = True) -> str | None:
    """Ask one question. Returns the answer, or None if skipped. Raises Pause."""
    print(question + ("  (Optional: press Enter to skip.)" if optional else ""))
    try:
        answer = input("You: ").strip()
    except EOFError:
        raise Pause
    if answer.lower() in ("pause", "quit"):
        raise Pause
    if answer.lower() == "skip" or not answer:
        if confirm:
            print("Skipped.\n")
        return None
    if confirm:
        print("Saved.\n")
    return answer


# --- Local model helpers ---------------------------------------------------
def llm_json(system: str, user: str, temperature: float = 0.2) -> dict | None:
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            format="json",
            options={"temperature": temperature},
        )
        result = json.loads(response["message"]["content"])
        return result if isinstance(result, dict) else None
    except Exception as e:
        print(f"(The local model couldn't help with this step: {e})")
        return None


FOLLOW_UP_MAX_WORDS = 40  # longer answers are already detailed; don't tire the worker


def generate_follow_up(domain: str, question: str, answer: str) -> str | None:
    if len(answer.split()) >= FOLLOW_UP_MAX_WORDS:
        return None
    result = llm_json(
        "You are a considerate interviewer drawing out a worker's professional expertise in "
        f"{domain}. Answering takes effort, so follow-ups must be rare. Given one question and "
        "the worker's answer, return an empty string UNLESS the answer is vague or general "
        "(no concrete detail, example, cue or reason). If the answer already names concrete "
        "things, return an empty string. When you do ask, ask ONE short question about the gap. "
        "Never ask about health, disability or personal details. "
        'Output JSON: {"follow_up": "question or empty string"}',
        f"Question: {question}\nWorker's answer: {answer}",
        temperature=0,
    )
    follow_up = str((result or {}).get("follow_up") or "").strip()
    return follow_up if len(follow_up) > 10 else None


def generate_case_probes(domain: str, story: str, timeline: str) -> list[str]:
    result = llm_json(
        "You are interviewing a worker using the Critical Decision Method to capture their "
        f"expertise in {domain}. Based on their story, write exactly 4 short follow-up "
        "questions that refer to specific details of THIS story: (1) the cues they noticed at "
        "the key moment, (2) other options they considered and why they rejected them, "
        "(3) what someone less experienced would have done, (4) a what-if: how they'd act if "
        "one key detail were different. Never ask about health, disability or personal details. "
        'Output JSON: {"questions": ["...", "...", "...", "..."]}',
        f"Story: {story}\nKey moments: {timeline or '(not given)'}",
        temperature=0.4,
    )
    questions = [str(q).strip() for q in (result or {}).get("questions", []) if str(q).strip()]
    return questions[:4] if len(questions) >= 2 else CDM_FALLBACK_PROBES


def generate_sample_task(domain: str, avoid: list[str]) -> str | None:
    result = llm_json(
        f"Write one realistic, small task that a client might post for a freelancer skilled in "
        f"{domain}. 2-3 sentences, concrete details, no solution. "
        'Output JSON: {"task": "..."}',
        "Make it different from these earlier tasks: " + json.dumps(avoid) if avoid else "Go.",
        temperature=0.9,
    )
    task = str((result or {}).get("task") or "").strip()
    return task or None


# --- Asking an item, with an optional adaptive follow-up -------------------
def ask_item(state, module, domain, item, question, followups, case_id=None) -> str | None:
    answer = ask(question)
    record(state, module=module, domain=domain, case_id=case_id, item=item,
           question=question, answer=answer)
    if answer and followups:
        print("(Thinking about a follow-up...)")
        follow_up = generate_follow_up(domain, question, answer)
        if follow_up:
            follow_answer = ask(follow_up, optional=True)
            record(state, module=module, domain=domain, case_id=case_id, item=f"{item}/follow_up",
                   question=follow_up, answer=follow_answer)
    return answer


# --- Modules ---------------------------------------------------------------
def run_knowledge_audit(state, domain, followups) -> None:
    done = recorded_items(state, "knowledge_audit", domain)
    total = len(KNOWLEDGE_AUDIT)
    for idx, (item, template) in enumerate(KNOWLEDGE_AUDIT, start=1):
        if item in done:
            continue
        print(f"Knowledge audit | {domain} | question {idx} of {total}")
        ask_item(state, "knowledge_audit", domain, item, template.format(domain=domain), followups)
    offer_notes(state, f"knowledge_audit|{domain}", domain,
                [e for e in state["entries"] if e["module"] == "knowledge_audit" and e["domain"] == domain])


def _open_case(state, module, domain) -> dict | None:
    for case in state["cases"]:
        if case["module"] == module and case["domain"] == domain and case["status"] == "in_progress":
            return case
    return None


def run_tough_case(state, domain, followups) -> None:
    case = _open_case(state, "critical_decision", domain)
    if case is None:
        case = {"id": f"case-{uuid.uuid4().hex[:8]}", "module": "critical_decision", "domain": domain,
                "status": "in_progress", "questions": [[i, q.format(domain=domain)] for i, q in CDM_OPENING],
                "probes_ready": False, "created": _now()}
        state["cases"].append(case)
        save_state(state)
    else:
        print(f"Continuing your tough case in {domain}.\n")

    while True:
        done = recorded_items(state, "critical_decision", domain, case["id"])
        pending = [(i, q) for i, q in case["questions"] if i not in done]
        if not pending:
            if case["probes_ready"]:
                break
            answers = {e["item"]: e["answer"] for e in state["entries"] if e.get("case_id") == case["id"]}
            if not answers.get("story"):
                print("No story this time, and that's fine. You can come back to this anytime.\n")
                case["status"] = "abandoned"
                save_state(state)
                return
            print("(Reading your story to prepare a few follow-up questions...)")
            probes = generate_case_probes(domain, answers["story"], answers.get("timeline") or "")
            case["questions"] += [[f"probe_{n}", q] for n, q in enumerate(probes, start=1)]
            case["questions"].append([CDM_CLOSING[0], CDM_CLOSING[1].format(domain=domain)])
            case["probes_ready"] = True
            save_state(state)
            continue
        item, question = pending[0]
        position = [i for i, _ in case["questions"]].index(item) + 1
        total = len(case["questions"]) if case["probes_ready"] else len(CDM_OPENING) + 5
        print(f"Tough case | {domain} | question {position} of about {total}")
        # Opening questions get adaptive follow-ups; the generated probes already are follow-ups.
        ask_item(state, "critical_decision", domain, item, question,
                 followups and item in ("story", "timeline"), case_id=case["id"])

    case["status"] = "done"
    save_state(state)
    offer_notes(state, case["id"], domain, [e for e in state["entries"] if e.get("case_id") == case["id"]])


def run_walkthrough(state, domain, followups) -> None:
    case = _open_case(state, "walkthrough", domain)
    if case is None:
        earlier = [c["sample_task"] for c in state["cases"] if c["module"] == "walkthrough" and c["domain"] == domain]
        while True:
            print("(Writing a sample task for you...)")
            task = generate_sample_task(domain, earlier)
            if not task:
                task = ask(f"Describe a typical task you might get in {domain}, and we'll walk through it.")
                if not task:
                    return
                break
            print(f"\nSample task:\n  {task}\n")
            choice = ask("Press Enter to use this task, or type 'new' for a different one.", confirm=False)
            if not choice or choice.lower() != "new":
                break
            earlier.append(task)
        case = {"id": f"walk-{uuid.uuid4().hex[:8]}", "module": "walkthrough", "domain": domain,
                "status": "in_progress", "sample_task": task,
                "questions": [[i, q] for i, q in WALKTHROUGH_QUESTIONS], "created": _now()}
        state["cases"].append(case)
        save_state(state)
    else:
        print(f"Continuing your walkthrough in {domain}.\n\nSample task:\n  {case['sample_task']}\n")

    done = recorded_items(state, "walkthrough", domain, case["id"])
    for idx, (item, question) in enumerate(case["questions"], start=1):
        if item in done:
            continue
        print(f"Walkthrough | {domain} | question {idx} of {len(case['questions'])}")
        ask_item(state, "walkthrough", domain, item, question, followups, case_id=case["id"])

    case["status"] = "done"
    save_state(state)
    offer_notes(state, case["id"], domain, [e for e in state["entries"] if e.get("case_id") == case["id"]])


# --- Condensed expertise notes, approved by the worker ---------------------
def offer_notes(state, key, domain, entries) -> None:
    if key in state["notes_done"]:
        return
    answered = [e for e in entries if e.get("answer")]
    if not answered:
        state["notes_done"].append(key)
        save_state(state)
        return
    print("(Condensing your answers into short notes for your AI...)")
    transcript = "\n\n".join(f"Q: {e['question']}\nA: {e['answer']}" for e in answered)
    result = llm_json(
        "You condense a worker's interview answers into short expertise notes for their AI "
        f"representative, about {domain}. Use ONLY what the worker said, in their own words where "
        "possible. Never add advice, facts or examples of your own. Each note is one complete, "
        "self-contained sentence that makes sense without the interview (not a fragment). "
        "rules_of_thumb = things the worker does or always checks; cues_to_notice = signs that "
        "something is wrong or tricky; common_mistakes = errors people make; quality_standards = "
        "what a finished result has when done well. Put each point in only one category. "
        "Output JSON with exactly these keys, each a list of strings (empty if the worker said "
        'nothing relevant): {"rules_of_thumb": [], "cues_to_notice": [], "common_mistakes": [], '
        '"quality_standards": []}',
        transcript,
        temperature=0,
    )
    notes = {cat: [str(n).strip() for n in (result or {}).get(cat, []) if str(n).strip()]
             for cat in NOTE_CATEGORIES}
    if not any(notes.values()):
        print("(No notes this time; your answers are still saved and used as they are.)\n")
        state["notes_done"].append(key)
        save_state(state)
        return

    print(f"\nHere's what your AI would learn about {domain}:")
    for cat, label in NOTE_CATEGORIES.items():
        if notes[cat]:
            print(f"  {label}:")
            for note in notes[cat]:
                print(f"    - {note}")
    choice = ask("\nPress Enter to save these notes, or type 'no' to discard them. "
                 "(Your answers are kept either way.)", confirm=False)
    if choice and choice.lower() == "no":
        print("Notes discarded.\n")
    else:
        all_notes = load_notes()
        domain_notes = all_notes.setdefault(domain, {cat: [] for cat in NOTE_CATEGORIES})
        for cat, items in notes.items():
            existing = {n.lower() for n in domain_notes.setdefault(cat, [])}
            domain_notes[cat] += [n for n in items if n.lower() not in existing]
        _write_json(NOTES_PATH, all_notes)
        print(f"Notes saved to {NOTES_PATH}. You can edit that file anytime.\n")
    state["notes_done"].append(key)
    save_state(state)


def offer_pending_notes(state) -> None:
    """Offer notes for modules finished in an earlier session but not yet condensed."""
    for domain in {e["domain"] for e in state["entries"]}:
        if recorded_items(state, "knowledge_audit", domain) >= {i for i, _ in KNOWLEDGE_AUDIT}:
            offer_notes(state, f"knowledge_audit|{domain}", domain,
                        [e for e in state["entries"] if e["module"] == "knowledge_audit" and e["domain"] == domain])
    for case in state["cases"]:
        if case["status"] == "done":
            offer_notes(state, case["id"], case["domain"],
                        [e for e in state["entries"] if e.get("case_id") == case["id"]])


# --- Menu ------------------------------------------------------------------
def load_domains(state) -> list[str]:
    domains = []
    if VOICEPRINT_PATH.exists():
        with open(VOICEPRINT_PATH, "r", encoding="utf-8") as f:
            profile = json.load(f).get("worker_profile", {})
        domains = [str(d).strip() for d in profile.get("primary_domains") or [] if str(d).strip()]
    for e in state["entries"]:  # areas the worker added during earlier sessions
        if e["domain"] not in domains:
            domains.append(e["domain"])
    return domains


def progress(state, domain) -> dict:
    audit = len(recorded_items(state, "knowledge_audit", domain) & {i for i, _ in KNOWLEDGE_AUDIT})
    cases = [c for c in state["cases"] if c["domain"] == domain and c["status"] == "done"]
    return {
        "knowledge_audit": audit,
        "critical_decision": sum(c["module"] == "critical_decision" for c in cases),
        "walkthrough": sum(c["module"] == "walkthrough" for c in cases),
    }


def suggest_next(state, domains) -> tuple[str, str] | None:
    for module in MODULES:
        for domain in domains:
            p = progress(state, domain)
            if (module == "knowledge_audit" and p[module] < len(KNOWLEDGE_AUDIT)) or \
               (module != "knowledge_audit" and p[module] == 0):
                return module, domain
    return None


def choose(prompt: str, options: list[str], allow_new: bool = False) -> str | None:
    for n, option in enumerate(options, start=1):
        print(f"  {n}. {option}")
    extra = ", or type a new area name" if allow_new else ""
    print(f"{prompt} (number{extra}; 'quit' to stop)")
    try:
        answer = input("You: ").strip()
    except EOFError:
        return None
    if answer.lower() in ("quit", "pause", ""):
        return None
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        return options[int(answer) - 1]
    return answer if allow_new else choose(prompt, options, allow_new)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deeper, multi-session VAI expertise interview.")
    parser.add_argument("--no-followups", action="store_true",
                        help="Don't ask adaptive follow-up questions (shorter sessions).")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(errors="replace")  # never crash on an unprintable character
    except Exception:
        pass

    try:
        ollama.list()
    except Exception as e:
        print(f"[Error] Could not connect to local Ollama: {e}")
        return

    state = load_state()
    domains = load_domains(state)

    print("\n" + "=" * 60)
    print("Voiceprint AI (VAI) | Deeper Expertise Interview")
    print("=" * 60)
    print("This teaches your AI how you think, not just what you do. Each module is short.")
    print("Type 'skip' to skip a question (it won't be asked again) or 'pause' to stop;")
    print("every answer is saved as you go, and you can resume anytime.\n")

    try:
        offer_pending_notes(state)
        while True:
            if domains:
                print("Your progress:")
                for d in domains:
                    p = progress(state, d)
                    print(f"  {d}: knowledge audit {p['knowledge_audit']}/{len(KNOWLEDGE_AUDIT)}, "
                          f"tough cases {p['critical_decision']}, walkthroughs {p['walkthrough']}")
                nxt = suggest_next(state, domains)
                if nxt:
                    print(f"Suggested next: {MODULES[nxt[0]]} for {nxt[1]}.")
                print()
            else:
                print("No areas of expertise found in voiceprint.json yet. "
                      "You can type one below, or run interviewer.py first.\n")

            module_labels = [
                "Knowledge audit (about 10 min): what you notice, rules of thumb, common mistakes",
                "Tough case (about 15 min): walk through one real, difficult case",
                "Walkthrough (about 10 min): talk through how you'd tackle a sample task",
            ]
            picked = choose("Which module?", module_labels)
            if not picked:
                break
            module = list(MODULES)[module_labels.index(picked)]
            domain = choose("Which area?", domains, allow_new=True)
            if not domain:
                break
            if domain not in domains:
                domains.append(domain)
            print()
            {"knowledge_audit": run_knowledge_audit, "critical_decision": run_tough_case,
             "walkthrough": run_walkthrough}[module](state, domain, not args.no_followups)
            print(f"Finished: {MODULES[module]} for {domain}.\n")
    except Pause:
        print("\nPaused. Everything you've said is saved; run this again anytime to continue.")
        return
    except KeyboardInterrupt:
        print("\nStopped. Everything you've said so far is saved.")
        return
    print("\nThanks. Your answers are saved locally and your VAI node picks them up within a few minutes.")


if __name__ == "__main__":
    main()
