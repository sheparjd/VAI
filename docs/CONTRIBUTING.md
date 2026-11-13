# Contributing to Voiceprint AI (VAI)

Thank you for your interest in **Voiceprint AI (VAI)**! We welcome developers, AI engineers, accessibility advocates, and designers who want to help build decentralized, human-owned AI tools that empower disabled individuals to earn independent income.

---

## 1. Core Project Values

Before writing code, please read our core design docs so every contribution aligns with the project mission:
* **[System Architecture](docs/ARCHITECTURE.md):** Understand how we keep personal data local (`local_node/`) while connecting to the marketplace (`web_platform/`).
* **[Accessibility Guidelines](docs/ACCESSIBILITY.md):** Review our non-negotiable standards for keyboard navigation, screen readers, asynchronous pacing, and low-fatigue UX.

---

## 2. Local Development Setup

### Prerequisites
* **Python 3.10+**
* **[Ollama](https://ollama.com)** running locally with an open-weights model installed (for example, `ollama pull llama3.1`).

### Step 1: Fork & Clone
1. Click **Fork** at the top right of this GitHub repository to create your own copy.
2. Clone your fork locally:
   ```bash
   git clone https://github.com
   cd voiceprint-ai
   ```

### Step 2: Install Dependencies
```bash
python -m venv venv
# Activate on Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Activate on macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Step 3: Initialize Local Configuration
```bash
cp .env.example .env
cp local_node/voiceprint.example.json local_node/voiceprint.json
```

### Step 4: Run the Full Local Stack
Open two terminal windows to test the end-to-end bridge:

* **Terminal 1 (Start the Two-Sided Web Platform):**
  ```bash
  python -m uvicorn web_platform.main:app --reload --port 8080
  ```
  Visit `http://127.0.0.1:8080` to view both the **Employer Side** and **VAI / Worker Side**.

* **Terminal 2 (Run Your Local VAI Worker Agent):**
  ```bash
  python local_node/worker_agent.py
  ```

---

## 3. High-Impact Areas Looking for Contributors

If you are looking for a place to jump in, check the **Issues** tab or pick up one of these priority milestones:
1. **RAG Memory Integration:** Wire `VoiceprintMemoryStore.query_memory()` from `local_node/memory_store.py` directly into `worker_agent.py`'s task-drafting prompt.
2. **Offline Voice Support:** Add local **Whisper** (speech-to-text) and **Piper** (text-to-speech) options to `local_node/interviewer.py`.
3. **Node Authentication:** Implement token-based authentication so each local VAI node pairs securely with its corresponding worker profile on `web_platform`.
4. **UI & Screen-Reader Polish:** Audit `web_platform/main.py` for ARIA live-region announcements and high-contrast display modes.

---

## 4. Submitting a Pull Request (PR)

1. Create a new branch for your feature or bug fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Keep your changes focused and modular.
3. Verify that your changes do **not** commit private files (`voiceprint.json`, `.env`, `*.db`, or `local_node/data/*`).
4. Run through the checklist in [docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md) if you modified any user interface or CLI prompts.
5. Push your branch to your fork and open a **Pull Request** against `main` with a clear summary of what your change improves.

---

## Questions or Ideas?
Open a **GitHub Issue** or start a discussion—we'd love to hear your thoughts on building inclusive, human-first AI infrastructure!
