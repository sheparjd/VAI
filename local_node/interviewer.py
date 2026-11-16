import json
import os
from datetime import datetime
from pathlib import Path
import ollama

# Configuration
MODEL_NAME = os.getenv("OLLAMA_MODEL", "llama3.1")
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("VAI_DATA_DIR") or BASE_DIR / "data")
TRANSCRIPT_PATH = DATA_DIR / "interview_transcript.json"
VOICEPRINT_PATH = BASE_DIR / "voiceprint.json"

# Accessible, low-fatigue core questions (one at a time)
INTERVIEW_QUESTIONS = [
    "What name or alias would you like employers to see on your VAI profile?",
    "In a couple of sentences, what kinds of problems do you enjoy solving or what skills do you bring?",
    "List the specific areas you're genuinely expert in, separated by commas. (For example: Python backend development, SQL data cleanup, technical documentation)",
    "What kinds of work are outside your expertise, so your AI should turn them down even though they're not off-limits? (For example: poetry, legal contracts, graphic design)",
    "How would you describe your ideal communication style? (For example: direct and concise, warm and detailed, bullet points over long paragraphs)",
    "What types of tasks or requests should your AI representative ALWAYS turn down automatically?",
    "How many hours do you typically need to review and approve work before it gets sent to an employer?",
    "Share one short example of how you would explain a complex idea or solve a problem in your own words."
]


def check_ollama_ready(model: str) -> bool:
    """Verify Ollama is running locally before starting the interview."""
    try:
        ollama.list()
        return True
    except Exception as e:
        print(f"\n[Error] Could not connect to local Ollama service: {e}")
        print("Make sure Ollama is running (try: 'ollama serve' or open the Ollama app).")
        return False


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def load_transcript() -> list[dict]:
    """Load answers from earlier sessions (empty list if none)."""
    if not TRANSCRIPT_PATH.exists():
        return []
    with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f) or []


def save_transcript(transcript: list[dict]) -> None:
    """Write the transcript safely: a crash mid-write can't corrupt earlier answers."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = TRANSCRIPT_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, TRANSCRIPT_PATH)


def backup_file(path: Path) -> Path | None:
    """Copy a file into data/backups/ before it's replaced. Returns the backup path."""
    if not path.exists():
        return None
    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.stem}.{_timestamp()}{path.suffix}"
    backup.write_bytes(path.read_bytes())
    return backup


def run_interview() -> tuple[list[dict], bool]:
    """Conduct a self-paced, one-question-at-a-time interview that can be resumed.

    Each answer is saved the moment it's given. Questions answered in earlier
    sessions are skipped; skipped questions are asked again next time.
    Returns the full transcript and whether it changed in this session.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    transcript = load_transcript()
    changed = False

    print("\n" + "=" * 60)
    print("🎙️  Voiceprint AI (VAI) — Local Training Interview")
    print("=" * 60)
    print("Take your time. There is no rush.")
    print("Type 'skip' to skip a question, or 'quit' to stop. Every answer is saved as you go.\n")

    answered = {item["question"] for item in transcript}
    if transcript:
        done = sum(q in answered for q in INTERVIEW_QUESTIONS)
        print(f"Welcome back. You've answered {done} of {len(INTERVIEW_QUESTIONS)} questions so far.")
        choice = input("Press Enter to continue where you left off, or type 'restart' to start over: ").strip().lower()
        if choice == "restart":
            backup = backup_file(TRANSCRIPT_PATH)
            transcript, answered = [], set()
            save_transcript(transcript)
            changed = True
            print(f"Starting over. Your previous answers were backed up to: {backup}\n")
        else:
            print()

    remaining = [q for q in INTERVIEW_QUESTIONS if q not in answered]
    if not remaining:
        print("You've already answered every question. Nothing left to ask.\n")

    for question in remaining:
        idx = INTERVIEW_QUESTIONS.index(question) + 1
        print(f"Question {idx} of {len(INTERVIEW_QUESTIONS)}:")
        print(f"🤖 VAI: {question}")

        answer = input("🧑 You: ").strip()

        if answer.lower() == "quit":
            print("\nStopping here. Your answers are saved; run this again anytime to continue.")
            break
        if answer.lower() == "skip" or not answer:
            print("⏭️  Skipped. I'll ask this one again next time.\n")
            continue

        transcript.append({
            "question": question,
            "answer": answer,
            "timestamp": datetime.now().isoformat()
        })
        save_transcript(transcript)
        changed = True
        print("✅ Saved.\n")

    return transcript, changed


def synthesize_voiceprint(transcript: list[dict], model: str) -> dict:
    """Use the local LLM to convert raw Q&A answers into a structured voiceprint.json."""
    print("🧠 Synthesizing your Voiceprint profile locally via Ollama...")

    qa_text = "\n\n".join(
        f"Q: {item['question']}\nA: {item['answer']}" for item in transcript
    )

    system_prompt = (
        "You are a precise configuration generator for Voiceprint AI. "
        "Convert the user's interview answers into a valid JSON object matching this exact structure:\n"
        "{\n"
        '  "schema_version": "0.1.0",\n'
        '  "worker_profile": {"display_name": "", "headline": "", "bio_summary": "", "primary_domains": []},\n'
        '  "communication_style": {"tone": "", "formatting_preferences": [], "sample_phrases": []},\n'
        '  "boundaries_and_guardrails": {\n'
        '    "never_accept_tasks_involving": [],\n'
        '    "require_human_approval": {"before_accepting_job": true, "before_submitting_final_deliverable": true, "when_confidence_is_low": true}\n'
        "  },\n"
        '  "competence_boundaries": {"outside_expertise": [], "decline_when_unsure": false},\n'
        '  "accessibility_and_pacing": {"preferred_input_mode": "voice_or_text", "max_active_tasks": 2, "review_window_hours": 24, "auto_pause_when_offline": true}\n'
        "}\n"
        "Rules:\n"
        "1. Output ONLY raw valid JSON. Do not include markdown fences or extra commentary.\n"
        "2. Never invent medical details, diagnoses, or private personal information.\n"
        "3. Keep 'before_submitting_final_deliverable' set to true.\n"
        "4. Fill 'primary_domains' with the areas the worker says they are expert in, and "
        "'outside_expertise' with the kinds of work they say are outside their expertise. "
        "Use the worker's own words; never add areas they didn't mention."
    )

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Interview Transcript:\n\n{qa_text}"}
        ],
        format="json"
    )

    raw_json = response["message"]["content"]
    return json.loads(raw_json)


def main():
    if not check_ollama_ready(MODEL_NAME):
        return

    transcript, changed = run_interview()

    if not transcript:
        print("No answers recorded. Exiting without generating voiceprint.json.")
        return
    if not changed and VOICEPRINT_PATH.exists():
        print("No new answers this session, so your existing voiceprint.json was left as is.")
        return

    try:
        voiceprint_data = synthesize_voiceprint(transcript, MODEL_NAME)
        # Keep any hand edits the worker made to the previous profile.
        backup = backup_file(VOICEPRINT_PATH)
        with open(VOICEPRINT_PATH, "w", encoding="utf-8") as f:
            json.dump(voiceprint_data, f, indent=2, ensure_ascii=False)

        print(f"\n🎉 Success! Your personal profile is saved to: {VOICEPRINT_PATH}")
        if backup:
            print(f"Your previous profile was backed up to: {backup}")
        print("Review or edit this JSON file anytime—you are always in control.")
    except Exception as e:
        print(f"\n[Error] Failed to generate JSON profile: {e}")
        print(f"Your raw answers are safely backed up in: {TRANSCRIPT_PATH}")


if __name__ == "__main__":
    main()
