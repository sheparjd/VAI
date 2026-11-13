import json
import os
from datetime import datetime
from pathlib import Path
import ollama

# Configuration
MODEL_NAME = os.getenv("OLLAMA_MODEL", "llama3.1")
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TRANSCRIPT_PATH = DATA_DIR / "interview_transcript.json"
VOICEPRINT_PATH = BASE_DIR / "voiceprint.json"

# Accessible, low-fatigue core questions (one at a time)
INTERVIEW_QUESTIONS = [
    "What name or alias would you like employers to see on your VAI profile?",
    "In a couple of sentences, what kinds of problems do you enjoy solving or what skills do you bring?",
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


def run_interview() -> list[dict]:
    """Conduct a self-paced, one-question-at-a-time interview."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    transcript = []

    print("\n" + "=" * 60)
    print("🎙️  Voiceprint AI (VAI) — Local Training Interview")
    print("=" * 60)
    print("Take your time. There is no rush.")
    print("Type 'skip' to skip a question, or 'quit' to save and exit anytime.\n")

    for idx, question in enumerate(INTERVIEW_QUESTIONS, start=1):
        print(f"Question {idx} of {len(INTERVIEW_QUESTIONS)}:")
        print(f"🤖 VAI: {question}")

        answer = input("🧑 You: ").strip()

        if answer.lower() == "quit":
            print("\nSaving progress and stopping early. You can resume anytime.")
            break
        if answer.lower() == "skip" or not answer:
            print("⏭️  Skipped.\n")
            continue

        transcript.append({
            "question": question,
            "answer": answer,
            "timestamp": datetime.now().isoformat()
        })
        print("✅ Saved.\n")

    with open(TRANSCRIPT_PATH, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2)

    return transcript


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
        '  "accessibility_and_pacing": {"preferred_input_mode": "voice_or_text", "max_active_tasks": 2, "review_window_hours": 24, "auto_pause_when_offline": true}\n'
        "}\n"
        "Rules:\n"
        "1. Output ONLY raw valid JSON. Do not include markdown fences or extra commentary.\n"
        "2. Never invent medical details, diagnoses, or private personal information.\n"
        "3. Keep 'before_submitting_final_deliverable' set to true."
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

    transcript = run_interview()

    if not transcript:
        print("No answers recorded. Exiting without generating voiceprint.json.")
        return

    try:
        voiceprint_data = synthesize_voiceprint(transcript, MODEL_NAME)
        with open(VOICEPRINT_PATH, "w", encoding="utf-8") as f:
            json.dump(voiceprint_data, f, indent=2)

        print(f"\n🎉 Success! Your personal profile is saved to: {VOICEPRINT_PATH}")
        print("Review or edit this JSON file anytime—you are always in control.")
    except Exception as e:
        print(f"\n[Error] Failed to generate JSON profile: {e}")
        print(f"Your raw answers are safely backed up in: {TRANSCRIPT_PATH}")


if __name__ == "__main__":
    main()
