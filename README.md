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
git clone https://github.com/sheparjd/VAI.git
cd VAI
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

### 5. Start Your Local VAI Node
In a second terminal (with Ollama running):
```bash
ollama pull nomic-embed-text   # small (~274 MB) local embedding model for your personal memory
python local_node/worker_agent.py
```
The node polls the platform for open tasks, drafts each one with your local Ollama model, and sends the draft to your Worker dashboard for approval. Without it, tasks stay `OPEN` and nothing is drafted. Set `OLLAMA_MODEL` to choose a model, and `PLATFORM_API_URL` if the platform isn't at `http://127.0.0.1:8080`.

For each task, the node looks up the most relevant parts of your **personal memory**: your interview answers, any `.txt`/`.md` files you put in `local_node/data/knowledge/`, and work you've previously approved. It learns from your reviews: when you approve a draft (edited or not) or decline it, the node records the outcome locally in `local_node/data/corrections.jsonl` and adds your final answer to its memory. All of this stays on your machine. If the embedding model isn't installed, the node falls back to using your interview transcript alone.

Before drafting, the node checks whether each task is within your expertise, using the areas you listed in the interview (`primary_domains`) and the kinds of work you said are outside it (`competence_boundaries.outside_expertise` in `voiceprint.json`). Tasks clearly outside your expertise are declined with a reason shown on your dashboard; borderline ones are still drafted but flagged "Borderline expertise" so you can decide. Set `decline_when_unsure` to `true` to decline borderline tasks too.

The interview can be paused and resumed: answers are saved as you go, and running `python local_node/interviewer.py` again picks up where you left off.

### 6. Teach Your VAI How You Think (Optional, Ongoing)
```bash
python local_node/deep_interview.py
```
The basic interview captures who you are; the deeper interview captures how you think, one area of expertise at a time. It's based on cognitive task analysis, the methods researchers use to study expert judgment, and has three short modules:

* **Knowledge audit** (about 10 min): what you notice that others miss, your rules of thumb, warning signs, common mistakes, and what "done well" looks like.
* **Tough case** (about 15 min): tell one real, difficult case from your work; your local model then asks follow-up questions about that specific story.
* **Walkthrough** (about 10 min): your local model writes a realistic sample task, and you talk through how you'd tackle it.

Do as many or as few as you like, in any order, across as many sessions as you need. Every answer is saved immediately; type `skip` to skip a question for good, or `pause` to stop and resume later. Your local model may ask an optional follow-up when an answer is brief (run with `--no-followups` for shorter sessions). After each module it condenses your answers into short notes, using only your words, and you approve them before they're saved to `local_node/data/expertise_notes.json` (editable anytime). Your running VAI node picks up new answers and notes within about 5 minutes.

### 7. Run Several VAIs (Testing With Colleagues)
The marketplace supports any number of VAIs. Each runs its own node with its own **profile**, a folder under `local_node/profiles/<name>/` (git-ignored) that holds that VAI's voiceprint, interview answers, memory and marketplace token. Choose a profile with `VAI_PROFILE`. Without it, the original `local_node/voiceprint.json` and `local_node/data/` are used.

To build test VAIs from colleagues without them installing anything:

1. Build the questionnaire, then email `questionnaire/vai_questionnaire.html` as an attachment (zip it if your mail system blocks `.html`):
   ```bash
   python local_node/make_questionnaire.py --sender "Your name"
   ```
   It opens in any browser and is blocked from making network requests. It autosaves in the colleague's own browser, and **Save my answers** downloads a `.json` file they email back. It covers the basic interview plus, optionally, the deeper interview for one area, with fixed questions in place of the adaptive follow-ups.
2. Import each returned file. This writes the profile and builds its voiceprint with your local model:
   ```bash
   python local_node/import_answers.py vai-answers-alice.json --profile alice
   ```
   Check `local_node/profiles/alice/voiceprint.json` (the name, headline, bio, areas and boundaries are what the marketplace shows), then delete the answers file.
3. Start a node per VAI, each in its own terminal (PowerShell shown):
   ```powershell
   $env:VAI_PROFILE = "alice"; python local_node/worker_agent.py
   ```

Each node registers its VAI's public card with the platform and receives its own token. Employers choose which VAI to hire, each VAI has its own dashboard under `/worker`, and a node only ever sees its own tasks. All nodes share one Ollama model, so running several costs little extra memory; they draft one after another.

The questionnaire is a development tool for colleagues. Real workers use the one-question-at-a-time interviews above (see [ACCESSIBILITY.md](docs/ACCESSIBILITY.md)).

### Environments
Dev, staging and production run the same code with separate configuration and data. See [docs/ENVIRONMENTS.md](docs/ENVIRONMENTS.md) for what each one requires and what the platform can know about a worker.


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
