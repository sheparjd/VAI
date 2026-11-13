import json
import os
from datetime import datetime
from pathlib import Path
import ollama

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VOICEPRINT_PATH = BASE_DIR / "voiceprint.json"
TRANSCRIPT_PATH = DATA_DIR / "interview_transcript.json"
DRAFTS_DIR = DATA_DIR / "drafts"


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
    """Load past Q&A answers as lightweight few-shot memory until ChromaDB is wired up."""
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
        '  "confidence": "HIGH" or "LOW",\n'
        '  "draft_deliverable": "Your complete drafted response written in the worker\'s authentic style (or empty string if DECLINE)"\n'
        "}"
    )

    user_prompt = (
        f"Incoming Employer Task:\n"
        f"Title: {task['title']}\n"
        f"Description: {task['description']}\n"
        f"Requirements: {task.get('requirements', 'None specified')}"
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


def human_review_gate(task: dict, result: dict, voiceprint: dict):
    """Pause execution and let the human worker approve, edit, or reject the AI's draft."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    require_approval = (
        voiceprint.get("boundaries_and_guardrails", {})
        .get("require_human_approval", {})
        .get("before_submitting_final_deliverable", True)
    )

    print("\n" + "-" * 60)
    print(f"TASK: {task['title']}")
    print(f"VAI Decision: {result.get('decision')} (Confidence: {result.get('confidence')})")
    print(f"Reasoning: {result.get('reason')}")
    print("-" * 60)

    if result.get("decision") == "DECLINE":
        print("VAI automatically declined this task based on your personal boundaries.")
        return

    print("\n--- DRAFTED DELIVERABLE ---\n")
    print(result.get("draft_deliverable", ""))
    print("\n---------------------------\n")

    if require_approval:
        choice = input("Human Approval Gate — [A]pprove & save, [R]eject draft, or [S]kip? ").strip().lower()
        if choice == "a":
            filename = f"approved_{task['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            out_path = DRAFTS_DIR / filename
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"task": task, "result": result, "status": "APPROVED_BY_HUMAN"}, f, indent=2)
            print(f"Approved! Deliverable saved to: {out_path}")
        else:
            print("Draft rejected or skipped. Nothing was sent.")


def run_local_simulation():
    """Test the local worker agent against sample marketplace tasks."""
    model = get_available_model()
    if not model:
        return

    voiceprint = load_voiceprint()
    if not voiceprint:
        return

    examples = load_interview_examples()

    # Sample tasks to test both normal work and boundary enforcement
    sample_tasks = [
        {
            "id": "task_001",
            "title": "Summarize a 3-step customer onboarding workflow",
            "description": "Write a clear, structured guide explaining how a new user creates an account, connects their email, and runs their first report.",
            "requirements": "Keep it concise and easy to read."
        },
        {
            "id": "task_002",
            "title": "Live Zoom Sales Representative",
            "description": "Join live video calls with prospective clients for 4 hours a day to pitch software.",
            "requirements": "Must be on camera and respond in real time."
        }
    ]

    print(f"\nVoiceprint AI Worker Agent active (Model: {model})")
    print(f"Loaded profile for: {voiceprint.get('worker_profile', {}).get('display_name', 'Worker')}")

    for task in sample_tasks:
        print(f"\nEvaluating incoming task '{task['title']}'...")
        result = evaluate_and_draft_task(task, voiceprint, examples, model)
        human_review_gate(task, result, voiceprint)


if __name__ == "__main__":
    run_local_simulation()
