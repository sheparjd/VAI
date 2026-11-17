import http.client
import json
import os
import time
from urllib.parse import urlparse
import ollama

import feedback

import profile_paths
from profile_paths import DATA_DIR, VOICEPRINT_PATH
TRANSCRIPT_PATH = DATA_DIR / "interview_transcript.json"

_platform = urlparse(os.getenv("PLATFORM_API_URL", "http://127.0.0.1:8080"))
PLATFORM_SCHEME = (_platform.scheme or "http").lower()
PLATFORM_HOST = _platform.hostname or "127.0.0.1"
PLATFORM_PORT = _platform.port or (443 if PLATFORM_SCHEME == "https" else 8080)
PLATFORM_ID = f"{PLATFORM_SCHEME}://{PLATFORM_HOST}:{PLATFORM_PORT}"  # tags local records by platform
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
POLL_INTERVAL_SECONDS = 5
# After this many failed AI attempts on one task, stop retrying it until the
# node restarts, so one bad task can't block the rest of the queue.
MAX_ATTEMPTS_PER_TASK = 3
MEMORY_RESYNC_SECONDS = 300  # re-read interview answers, notes and documents this often


class DraftError(Exception):
    """The local model failed to produce a usable decision/draft."""


def get_available_model() -> str | None:
    """Verify Ollama is running and select an installed model."""
    preferred = os.getenv("OLLAMA_MODEL") or "llama3.1"
    try:
        response = ollama.list()
        raw_models = response.get("models", []) if isinstance(response, dict) else getattr(response, "models", [])
        installed = []
        for m in raw_models:
            name = m.get("name") or m.get("model") if isinstance(m, dict) else getattr(m, "model", None)
            if name:
                installed.append(name)

        if not installed:
            print("[Error] No Ollama models found. Run 'ollama pull llama3.1' first.")
            return None

        # "llama3.1" is installed as "llama3.1:latest"; match either form.
        for name in installed:
            if name == preferred or name == f"{preferred}:latest":
                return name
        # Never draft with an embedding-only model (e.g. nomic-embed-text).
        chat_models = [n for n in installed if "embed" not in n.lower()]
        if not chat_models:
            print("[Error] Only embedding models are installed. Run 'ollama pull llama3.1' first.")
            return None
        print(f"[Note] Model '{preferred}' isn't installed; using '{chat_models[0]}' instead.")
        return chat_models[0]
    except Exception as e:
        print(f"[Error] Could not connect to Ollama: {e}")
        return None


def load_voiceprint() -> dict | None:
    """Load the worker's personal voiceprint.json configuration."""
    if not VOICEPRINT_PATH.exists():
        print(f"[Error] No voiceprint.json found at {VOICEPRINT_PATH}.")
        print("Run 'python local_node/interviewer.py' first to create your profile.")
        return None

    with open(VOICEPRINT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_interview_examples() -> str:
    """Load past Q&A answers as lightweight few-shot memory."""
    if not TRANSCRIPT_PATH.exists():
        return ""

    with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
        transcript = json.load(f)

    if not transcript:
        return ""

    lines = ["Examples of how the worker thinks and communicates:"]
    for item in transcript:
        lines.append(f"- Prompt: {item['question']}\n  Worker's Answer: {item['answer']}")
    return "\n".join(lines)


def evaluate_and_draft_task(task: dict, voiceprint: dict, examples: str, model: str) -> dict:
    """Check task against worker guardrails and draft a response if allowed."""
    profile = voiceprint.get("worker_profile", {})
    style = voiceprint.get("communication_style", {})
    boundaries = voiceprint.get("boundaries_and_guardrails", {})
    forbidden = boundaries.get("never_accept_tasks_involving", [])

    system_prompt = (
        f"You are the local Voiceprint AI (VAI) representative acting on behalf of {profile.get('display_name', 'the worker')}.\n"
        f"Headline: {profile.get('headline', '')}\n"
        f"Bio: {profile.get('bio_summary', '')}\n"
        f"Communication Tone: {style.get('tone', 'Clear and professional')}\n"
        f"Formatting Preferences: {', '.join(style.get('formatting_preferences', []))}\n\n"
        f"{examples}\n\n"
        "STRICT GUARDRAILS:\n"
        f"You MUST decline any task involving: {json.dumps(forbidden)}\n\n"
        "Output ONLY a valid JSON object with this exact schema:\n"
        "{\n"
        '  "decision": "ACCEPT" or "DECLINE",\n'
        '  "reason": "Brief explanation of why this matches or violates the worker\'s boundaries",\n'
        '  "draft_deliverable": "Your complete drafted response written in the worker\'s authentic style (or empty string if DECLINE)"\n'
        "}"
    )

    user_prompt = (
        f"Incoming Employer Task:\n"
        f"Title: {task['title']}\n"
        f"Description: {task['description']}"
    )

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        format="json"
    )

    raw_json = response["message"]["content"] if isinstance(response, dict) else response.message.content
    try:
        result = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise DraftError(f"model returned invalid JSON ({e})") from e
    if not isinstance(result, dict):
        raise DraftError("model returned JSON that isn't an object")

    decision = str(result.get("decision", "")).strip().upper()
    if decision not in ("ACCEPT", "DECLINE"):
        raise DraftError(f"model returned an unknown decision: {result.get('decision')!r}")
    draft = result.get("draft_deliverable", "")
    if not isinstance(draft, str):
        draft = json.dumps(draft, indent=2)
    if decision == "ACCEPT" and not draft.strip():
        raise DraftError("model accepted the task but returned an empty draft")

    return {
        "decision": decision,
        "reason": str(result.get("reason", "")),
        "draft_deliverable": draft if decision == "ACCEPT" else "",
    }


def _as_list(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in (value or []) if str(v).strip()]


def check_competence(task: dict, voiceprint: dict, memory_text: str, model: str) -> dict | None:
    """Decide whether a task is within the worker's expertise, before any drafting.

    Returns {"verdict": "IN_SCOPE" | "OUT_OF_SCOPE" | "UNSURE", "matched_area", "reason"},
    or None when the voiceprint says nothing about expertise (the check is skipped).
    This is a separate, short model call: judging scope on its own is more
    reliable than asking the model to judge and draft in one go.
    """
    profile = voiceprint.get("worker_profile", {})
    competence = voiceprint.get("competence_boundaries", {})
    expertise = _as_list(profile.get("primary_domains"))
    if not expertise:
        # Older or sparse voiceprints: fall back to the headline and bio.
        expertise = _as_list([profile.get("headline"), profile.get("bio_summary")])
        expertise = list(dict.fromkeys(expertise))  # drop duplicates, keep order
    if not expertise:
        return None
    outside = _as_list(competence.get("outside_expertise"))

    system_prompt = (
        "You decide whether an employer's task falls within ONE specific worker's professional expertise.\n"
        f"The worker's areas of expertise: {json.dumps(expertise)}\n"
        f"Areas the worker says are OUTSIDE their expertise: {json.dumps(outside)}\n\n"
        "Verdicts:\n"
        "- IN_SCOPE: doing this task well mainly needs knowledge or skills from the worker's areas, "
        "or is work a professional in those areas routinely does. Also IN_SCOPE if the memory below "
        "shows the worker has approved similar work before.\n"
        "- OUT_OF_SCOPE: doing it well mainly needs specialist knowledge from a different field, or it "
        "matches one of the 'outside' areas. General writing or research ability alone does NOT make a "
        "task in scope.\n"
        "- UNSURE: genuinely borderline.\n\n"
        f"{memory_text or ''}\n\n"
        "Output ONLY a JSON object: "
        '{"verdict": "IN_SCOPE" or "OUT_OF_SCOPE" or "UNSURE", '
        '"matched_area": "a short field name: for IN_SCOPE the worker area it uses, otherwise the field the task actually needs (e.g. Law)", '
        '"reason": "one short sentence"}'
    )
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task title: {task['title']}\nTask description: {task['description']}"},
        ],
        format="json",
        options={"temperature": 0},  # same task -> same verdict
    )
    raw_json = response["message"]["content"] if isinstance(response, dict) else response.message.content
    try:
        result = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise DraftError(f"competence check returned invalid JSON ({e})") from e
    verdict = str(result.get("verdict", "")).strip().upper().replace(" ", "_")
    if verdict not in ("IN_SCOPE", "OUT_OF_SCOPE", "UNSURE"):
        raise DraftError(f"competence check returned an unknown verdict: {result.get('verdict')!r}")
    area = str(result.get("matched_area") or "").strip()
    if area.lower() in ("none", "null", "n/a"):
        area = ""
    return {
        "verdict": verdict,
        "matched_area": area,
        "reason": str(result.get("reason", "")),
    }


def handle_task(task: dict, voiceprint: dict, memory_text: str, model: str) -> dict:
    """Competence check first; draft only if the task is within the worker's expertise."""
    scope = check_competence(task, voiceprint, memory_text, model)
    decline_when_unsure = bool(voiceprint.get("competence_boundaries", {}).get("decline_when_unsure", False))

    area = f" ({scope['matched_area']})" if scope and scope["matched_area"] else ""
    if scope:
        print(f" -> Expertise check: {scope['verdict']}{area}")
    if scope and (scope["verdict"] == "OUT_OF_SCOPE" or (scope["verdict"] == "UNSURE" and decline_when_unsure)):
        label = "Outside expertise" if scope["verdict"] == "OUT_OF_SCOPE" else "Possibly outside expertise"
        return {
            "decision": "DECLINE",
            "reason": f"{label}{area}: {scope['reason']}",
            "draft_deliverable": "",
        }

    result = evaluate_and_draft_task(task, voiceprint, memory_text, model)
    if scope and scope["verdict"] == "UNSURE":
        # Borderline: draft it, but make sure the worker sees the doubt when reviewing.
        result["reason"] = f"Borderline expertise{area}: {scope['reason']} {result['reason']}"
    return result


class BridgeAuthError(RuntimeError):
    """The platform rejected this node's token or registration key."""


_node_token: str | None = None  # this profile's token for the current platform


def _bridge_request(method: str, path: str, payload: dict | None = None,
                    extra_headers: dict | None = None):
    """Call the platform's bridge API directly via http.client; returns parsed JSON."""
    conn_cls = http.client.HTTPSConnection if PLATFORM_SCHEME == "https" else http.client.HTTPConnection
    conn = conn_cls(PLATFORM_HOST, PLATFORM_PORT, timeout=10)
    headers = dict(extra_headers or {})
    if _node_token:
        headers["Authorization"] = f"Bearer {_node_token}"
    try:
        if payload is None:
            conn.request(method, path, headers=headers)
        else:
            headers["Content-Type"] = "application/json"
            conn.request(method, path, body=json.dumps(payload), headers=headers)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status in (401, 403):
            raise BridgeAuthError(f"HTTP {resp.status}: {body}")
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {body}")
        return json.loads(body)
    finally:
        conn.close()


# --- Marketplace registration ----------------------------------------------
# The platform only ever receives this public card. Interview answers, deep
# interview notes, documents, local memory and draft history never leave
# this machine.
def public_card(voiceprint: dict) -> dict:
    profile = voiceprint.get("worker_profile", {})
    guardrails = voiceprint.get("boundaries_and_guardrails", {})
    return {
        "display_name": str(profile.get("display_name") or "VAI worker").strip()[:100],
        "headline": str(profile.get("headline") or "").strip()[:200],
        "bio_summary": str(profile.get("bio_summary") or "").strip()[:2000],
        "domains": [d[:100] for d in _as_list(profile.get("primary_domains"))][:20],
        "boundaries": [b[:200] for b in _as_list(guardrails.get("never_accept_tasks_involving"))][:20],
    }


def _load_credentials() -> dict:
    path = profile_paths.CREDENTIALS_PATH
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f) or {}


def _save_credentials(creds: dict) -> None:
    path = profile_paths.CREDENTIALS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2)
    os.replace(tmp, path)


def register_with_platform(voiceprint: dict) -> bool:
    """Publish (or refresh) this VAI's public card and keep its token for this platform.

    Tokens are stored per platform, so a token issued by a dev or staging
    platform is never sent to a different one.
    """
    global _node_token
    creds = _load_credentials()
    _node_token = (creds.get(PLATFORM_ID) or {}).get("token")
    reg_key = os.getenv("VAI_REGISTRATION_KEY")
    headers = {"X-VAI-Registration-Key": reg_key} if reg_key else {}
    try:
        result = _bridge_request("POST", "/api/bridge/register", public_card(voiceprint), headers)
    except BridgeAuthError as e:
        if not _node_token:
            print(f"[Error] The marketplace refused to register this VAI ({e}).")
            print("Check that VAI_REGISTRATION_KEY matches the platform's key.")
            return False
        # The platform no longer knows this token (e.g. its database was reset).
        print("[Bridge] The marketplace didn't recognise this VAI's token; registering again.")
        creds.pop(PLATFORM_ID, None)
        _save_credentials(creds)
        _node_token = None
        return register_with_platform(voiceprint)
    if result.get("token"):
        _node_token = result["token"]
        creds[PLATFORM_ID] = {"token": _node_token, "vai_id": result.get("vai_id")}
        _save_credentials(creds)
        print(f"[Bridge] Registered as VAI #{result.get('vai_id')} on {PLATFORM_ID}.")
    else:
        print(f"[Bridge] Public card refreshed for VAI #{result.get('vai_id')} on {PLATFORM_ID}.")
    return True


def connect(voiceprint: dict) -> bool:
    """Register with the platform, waiting for it if it's down. False = stop."""
    while True:
        try:
            return register_with_platform(voiceprint)
        except Exception as e:
            print(f"[Waiting] Web platform unreachable ({e}). Retrying in {POLL_INTERVAL_SECONDS}s...")
            time.sleep(POLL_INTERVAL_SECONDS)


def fetch_open_tasks() -> list[dict]:
    """Poll /api/bridge/tasks for OPEN tasks."""
    return _bridge_request("GET", "/api/bridge/tasks")


def submit_draft(payload: dict) -> dict:
    """Post an AI draft to /api/bridge/submit. Returns the platform's response."""
    return _bridge_request("POST", "/api/bridge/submit", payload)


def fetch_outcomes(task_ids: list[int]) -> list[dict]:
    """Ask which drafted tasks the worker has since approved or declined."""
    if not task_ids:
        return []
    return _bridge_request("GET", "/api/bridge/outcomes?ids=" + ",".join(map(str, task_ids)))


def open_memory_store():
    """Open the local RAG memory, or return None to fall back to the plain transcript."""
    try:
        from memory_store import VoiceprintMemoryStore
        store = VoiceprintMemoryStore()
        stats = store.sync_all()
        print(f"[Memory] Local memory ready: {stats['interview']} interview answers, "
              f"{stats['deep_interview']} deep-interview answers, {stats['expertise_notes']} note groups, "
              f"{stats['knowledge']} document chunks, {stats['reviewed_work']} reviewed tasks "
              f"({stats['added']} newly indexed).")
        return store
    except Exception as e:
        print(f"[Memory] Local memory unavailable ({e}).")
        print("[Memory] Falling back to the full interview transcript in every prompt.")
        return None


def learn_from_outcomes(memory) -> None:
    """Record how the worker handled earlier drafts, and add them to local memory."""
    pending = feedback.pending_drafts(PLATFORM_ID)
    if not pending:
        return
    learned = 0
    for outcome in fetch_outcomes(list(pending)):
        draft = pending.get(outcome["id"])
        if not draft:
            continue
        if outcome["title"] != draft["title"]:
            # Task id now belongs to a different task (e.g. platform DB was reset).
            feedback.discard_draft(draft, "task id reused by a different task")
            continue
        rec = feedback.record_outcome(draft, outcome)
        learned += 1
        if rec["outcome"] == "APPROVED" and not rec["edited"]:
            note = "approved unchanged"
        elif rec["outcome"] == "APPROVED":
            note = f"approved with edits ({rec['similarity']:.0%} similar to the AI draft)"
        else:
            note = "declined by you"
        print(f"[Learned] Task #{rec['task_id']} '{rec['title']}': {note}.")
    if learned and memory:
        memory.sync_all()


def run_bridge_loop():
    """Continuously poll the web platform for new tasks and submit AI drafts."""
    model = get_available_model()
    if not model:
        return

    voiceprint = load_voiceprint()
    if not voiceprint:
        return

    if PLATFORM_SCHEME != "https" and PLATFORM_HOST not in LOCAL_HOSTS:
        print(f"[Error] {PLATFORM_ID} isn't HTTPS. A remote marketplace must use https:// "
              "so this VAI's token can't be read in transit.")
        return

    worker_name = voiceprint.get("worker_profile", {}).get("display_name", "Worker")
    card = public_card(voiceprint)

    print("\n" + "=" * 60)
    print(f"VAI Local Node | {profile_paths.describe()} | Profile: {worker_name} | Model: {model}")
    print(f"Marketplace: {PLATFORM_ID}")
    print("Shared with the marketplace (public card only):")
    print(f"  Name: {card['display_name']} | Headline: {card['headline']}")
    print(f"  Areas: {'; '.join(card['domains']) or '-'}")
    print(f"  Never accepts: {'; '.join(card['boundaries']) or '-'}")
    print("Kept on this machine: interview answers, expertise notes, documents, memory "
          f"and draft history ({DATA_DIR}).")
    print("Press Ctrl+C to pause your local VAI node anytime.")
    print("=" * 60 + "\n")

    try:
        if not connect(voiceprint):
            return
    except KeyboardInterrupt:
        print("\nLocal VAI node paused. Goodbye!")
        return

    memory = open_memory_store()
    transcript_examples = None if memory else load_interview_examples()

    failures: dict[int, int] = {}  # task id -> failed AI attempts
    last_sync = time.time()

    try:
        while True:
            try:
                open_tasks = fetch_open_tasks()
            except BridgeAuthError:
                print("[Bridge] Token rejected; registering this VAI again.")
                if not connect(voiceprint):
                    return
                continue
            except Exception as e:
                print(f"[Waiting] Web platform unreachable ({e}). Retrying in {POLL_INTERVAL_SECONDS}s...")
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            try:
                learn_from_outcomes(memory)
            except Exception as e:
                print(f"[Memory] Could not record review outcomes yet ({e}).")

            # Pick up new interview answers, notes and documents without a restart.
            if memory and time.time() - last_sync >= MEMORY_RESYNC_SECONDS:
                last_sync = time.time()
                try:
                    stats = memory.sync_all()
                    if stats["added"] or stats["removed"]:
                        print(f"[Memory] Updated: {stats['added']} new, {stats['removed']} removed.")
                except Exception as e:
                    print(f"[Memory] Could not refresh memory ({e}).")

            for task in open_tasks:
                task_id = task["id"]
                if failures.get(task_id, 0) >= MAX_ATTEMPTS_PER_TASK:
                    continue  # already gave up on this one; leave it for the worker

                print(f"[New Task #{task_id}] '{task['title']}' — Checking expertise and guardrails...")
                try:
                    if memory:
                        examples = memory.query_memory(f"{task['title']}\n{task['description']}")
                    else:
                        examples = transcript_examples
                    result = handle_task(task, voiceprint, examples, model)
                except Exception as e:
                    failures[task_id] = failures.get(task_id, 0) + 1
                    print(f" -> [AI Error] Could not draft task #{task_id} "
                          f"(attempt {failures[task_id]}/{MAX_ATTEMPTS_PER_TASK}): {e}")
                    if failures[task_id] >= MAX_ATTEMPTS_PER_TASK:
                        print(f" -> Skipping task #{task_id}. It stays OPEN for you to answer "
                              "on the Worker dashboard.\n")
                    continue

                try:
                    response = submit_draft({"task_id": task_id, **result})
                except Exception as e:
                    print(f" -> [Waiting] Could not submit task #{task_id} ({e}). Will retry.\n")
                    break  # platform likely down; re-poll after the sleep
                failures.pop(task_id, None)
                if response.get("status") == "ignored":
                    print(f" -> Task #{task_id} was already handled on the dashboard; draft not used.\n")
                    continue
                if result["decision"] == "ACCEPT":
                    feedback.record_draft(task, result, model, PLATFORM_ID)
                print(f" -> Submitted to Worker Dashboard (Decision: {result['decision']})\n")

            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nLocal VAI node paused. Goodbye!")


if __name__ == "__main__":
    run_bridge_loop()
