import http.client
import json
import os
import time
from pathlib import Path
import ollama

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VOICEPRINT_PATH = BASE_DIR / "voiceprint.json"
TRANSCRIPT_PATH = DATA_DIR / "interview_transcript.json"

PLATFORM_HOST = "127.0.0.1"
PLATFORM_PORT = 8080
POLL_INTERVAL_SECONDS = 5


def get_available_model() -> str | None:
    """Verify Ollama is running and select an installed model."""
    preferred = os.getenv("OLLAMA_MODEL")
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

        if preferred and preferred in installed:
            return preferred
        return installed[0]
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
    return json.loads(raw_json)


def fetch_open_tasks() -> list[dict]:
    """Poll /api/bridge/tasks directly via http.client."""
    conn = http.client.HTTPConnection(PLATFORM_HOST, PLATFORM_PORT, timeout=10)
    try:
        conn.request("GET", "/api/bridge/tasks")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {body}")
        return json.loads(body)
    finally:
        conn.close()


def submit_draft(payload: dict) -> None:
    """Post AI draft to /api/bridge/submit directly via http.client."""
    conn = http.client.HTTPConnection(PLATFORM_HOST, PLATFORM_PORT, timeout=10)
    try:
        headers = {"Content-Type": "application/json"}
        conn.request("POST", "/api/bridge/submit", body=json.dumps(payload), headers=headers)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {body}")
    finally:
        conn.close()


def run_bridge_loop():
    """Continuously poll the web platform for new tasks and submit AI drafts."""
    model = get_available_model()
    if not model:
        return

    voiceprint = load_voiceprint()
    if not voiceprint:
        return

    examples = load_interview_examples()
    worker_name = voiceprint.get("worker_profile", {}).get("display_name", "Worker")

    print("\n" + "=" * 60)
    print(f"VAI Local Node Online | Profile: {worker_name} | Model: {model}")
    print(f"Polling marketplace at: http://{PLATFORM_HOST}:{PLATFORM_PORT}/api/bridge")
    print("Press Ctrl+C to pause your local VAI node anytime.")
    print("=" * 60 + "\n")

    while True:
        try:
            open_tasks = fetch_open_tasks()

            for task in open_tasks:
                print(f"[New Task #{task['id']}] '{task['title']}' — Evaluating against guardrails...")
                result = evaluate_and_draft_task(task, voiceprint, examples, model)

                payload = {
                    "task_id": task["id"],
                    "decision": result.get("decision", "ACCEPT"),
                    "reason": result.get("reason", ""),
                    "draft_deliverable": result.get("draft_deliverable", "")
                }

                submit_draft(payload)
                print(f" -> Submitted to Worker Dashboard (Decision: {payload['decision']})\n")

        except KeyboardInterrupt:
            print("\nLocal VAI node paused. Goodbye!")
            break
        except Exception as e:
            print(f"[Waiting] Web platform unreachable ({e}). Retrying in {POLL_INTERVAL_SECONDS}s...")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_bridge_loop()
