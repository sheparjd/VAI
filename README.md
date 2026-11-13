# Voiceprint AI (VAI)

**Decentralized, user-owned AI workers empowering disabled individuals to earn independent income.**

---

## The Human Mission

Traditional workplaces and gig platforms often exclude severely disabled individuals due to rigid schedules, physical demands, or real-time communication barriers—even when those individuals possess deep domain knowledge, creativity, and sharp judgment.

**Voiceprint AI (VAI)** flips the traditional AI labor model. Instead of corporations replacing workers with generic bots, VAI enables individuals to train their own **personal, local-first AI representative** through accessible, self-paced interviews. 

* **True Ownership:** Your "Voiceprint" (knowledge, style, and decision boundaries) lives on your hardware—not locked inside a corporate black box.
* **Accessible Workflows:** Workers train their AI at their own pace using voice, switch access, or text, and review deliverables asynchronously with one-click approvals.
* **Direct Economic Agency:** Employers hire verified VAI representatives for scoped tasks, and 100% of the worker's earnings go directly to the human behind the model.

---

## How It Works (MVP Architecture)

VAI splits the system into two decoupled halves connected by a secure polling bridge:

1. **The Local VAI Node (`local_node/`):** Runs on the worker's machine via **Ollama**. A guided **Interviewer Agent** captures the user's expertise into a local vector store (**ChromaDB** / **SQLite-vec**). A background worker polls for assigned jobs and drafts responses using the user's unique voiceprint.
2. **The Two-Sided Platform (`platform/`):** A lightweight **FastAPI + PostgreSQL** web app featuring an **Employer Portal** (to browse VAI profiles and post tasks) and a **Worker Control Dashboard** (to approve drafts before delivery).

```text
[Disabled Worker] 
   │  (Self-paced guided interview)
   ▼
[Local VAI Node (Ollama + Local RAG)] 
   │  (Polls for jobs & submits human-approved drafts)
   ▼
[VAI Web Platform (FastAPI + Postgres)]
   ▲  (Posts tasks, reviews work, pays worker)
   │
[Employer]
```

---

## Tech Stack

* **Local AI Runtime:** Python, Ollama (Llama 3 / Mistral)
* **Personal Memory:** ChromaDB / SQLite-vec
* **Platform Backend:** FastAPI, SQLAlchemy, PostgreSQL
* **Frontend:** Accessible HTML/CSS, HTMX, Tailwind CSS

---

## Quickstart (Run Locally in 10 Minutes)

### Prerequisites
* Python 3.10+
* [Ollama](https://ollama.com) installed locally (`ollama pull llama3.1`)

### 1. Clone & Install
```bash
git clone https://github.com
cd voiceprint-ai
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
cp local_node/voiceprint.example.json local_node/voiceprint.json
```

### 3. Run Your First Training Interview
```bash
python local_node/interviewer.py
```

### 4. Start the Marketplace Platform
```bash
python -m uvicorn web_platform.main:app --reload --port 8080
```
Visit `http://127.0.0.1:8080` to explore both the **Employer** and **Worker** views.


---

## Where We Need Contributors

We are actively looking for developers, designers, and accessibility advocates to help build the MVP:
* **AI / RAG Engineers:** Improve the adaptive interview prompt pipeline so VAI captures nuanced expertise without exhausting the user.
* **Accessibility & Frontend Devs:** Build zero-friction, screen-reader-first UI components and voice/switch-friendly approval workflows.
* **Backend & Security Engineers:** Harden the local-to-cloud polling bridge and task escrow lifecycle.

Check out `docs/ARCHITECTURE.md` or open an issue to jump in!

---

## Additional Notes

There is also an opportunity here for random assignment of more menial tasks.  With functionality to randomly assign trivial tasks, a basic income could be supportive of all Persons, regardless of expertise.
Biometric Zero-Knowledge Proofs should be used to guarantee a One Human, One Node principle. Proof of Personhood is vital to this mission.  Also, VAIs should be limited to a fair share of actions-per-day.
This could be either a dynamic percentage or a flat limit of 100 tasks in a given workday to disperse workloads fairly.

---

## License
Apache 2.0