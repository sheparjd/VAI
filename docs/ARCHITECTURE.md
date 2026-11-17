# Voiceprint AI (VAI) — System Architecture

## 1. Design Philosophy & Core Principles

Voiceprint AI (VAI) is built around three architectural pillars designed to empower disabled workers with genuine ownership and economic agency:

1. **Local-First Sovereignty:** A worker's personal knowledge, interview transcripts, and behavioral guardrails (`voiceprint.json`) never leave their local machine or private server. The central marketplace never stores raw personal training data.
2. **Asynchronous by Default:** Every interaction between employers, the AI representative, and the human worker is decoupled through a task queue. Workers operate at their own pace without real-time latency pressure.
3. **Human-in-the-Loop (HITL) Gatekeeping:** The local AI drafts deliverables and filters out boundary-violating tasks, but final submission and payout release always require explicit human approval.

---

## 2. High-Level System Overview

The system is split into two independent components connected via an outbound HTTP polling bridge:

```text
+-------------------------------------------------------+

|              LOCAL VAI NODE (local_node/)             |
|  * Runs privately on the worker's hardware            |
|  * Ollama LLM (Llama 3 / Mistral)                     |
|  * ChromaDB Vector Memory (memory_store.py)           |
|  * Guardrail & Profile Config (voiceprint.json)       |
+---------------------------+---------------------------+
                            |
           Outbound Polling | (http.client REST calls)
           GET /tasks       | POST /submit
                            v
+-------------------------------------------------------+

|           TWO-SIDED PLATFORM (web_platform/)          |
|  * FastAPI Backend + SQLAlchemy ORM                   |
|  * Employer Portal (/employer)                        |
|  * Worker Approval Dashboard (/worker)                |
+-------------------------------------------------------+
```

---

## 3. Component Breakdown

### A. Local VAI Node (`local_node/`)
* **`interviewer.py` (Training Pipeline):** Conducts a self-paced, one-question-at-a-time interview via local Ollama models. Each answer is saved to `data/interview_transcript.json` as it's given, so sessions can be paused and resumed. Synthesizes a structured `voiceprint.json` configuration, backing up the previous one to `data/backups/`.
* **`deep_interview.py` (Expertise Capture):** Optional, multi-session interview modules per area of expertise, based on cognitive task analysis: a *knowledge audit* (after Applied Cognitive Task Analysis), a *tough case* (after the Critical Decision Method, with follow-up questions generated from the worker's own story), and a *walkthrough* of a model-generated sample task (think-aloud). Brief answers may get one optional adaptive follow-up. Answers are saved immediately to `data/deep_interview.json`; after each module the model condenses them into notes (rules of thumb, cues, common mistakes, quality standards) using only the worker's words, which the worker approves before they're saved to `data/expertise_notes.json`.
* **`memory_store.py` (Personal RAG):** Uses a persistent local **ChromaDB** instance (`data/chroma_db/`, telemetry disabled) with embeddings from a small local Ollama model (`nomic-embed-text` by default, override with `VAI_EMBED_MODEL`). Indexes interview Q&As, deep-interview answers, approved expertise notes, `.txt`/`.md` documents in `data/knowledge/`, and reviewed work from `data/corrections.jsonl`. The worker node re-syncs every 5 minutes. Entries are keyed by content hash, so a sync only embeds new or changed text.
* **`feedback.py` (Learning from Review):** Keeps a local record of every draft the node submits (`data/drafts.jsonl`) and how the worker resolved it (`data/corrections.jsonl`: approved unchanged, approved with edits plus a similarity score, or declined). The platform only stores final deliverables; the AI-draft-versus-final comparison never leaves the worker's machine.
* **`worker_agent.py` (Autonomous Drafter):** Polls the marketplace for `OPEN` tasks. For each one it first runs a separate **expertise check** against the worker's `primary_domains` (falling back to headline and bio) and `competence_boundaries.outside_expertise`: out-of-scope tasks are declined with a reason, and borderline ones are drafted with a "Borderline expertise" note for the worker (or declined if `decline_when_unsure` is true). It then evaluates the task against `never_accept_tasks_involving` rules in `voiceprint.json`, retrieves the most relevant memory for that task from `memory_store.py`, and drafts deliverables in the worker's authentic voice. Each poll also checks `/api/bridge/outcomes` for drafts the worker has since reviewed, and records them via `feedback.py`.

All local data lives under `local_node/data/` (git-ignored); set `VAI_DATA_DIR` to use a different folder. With `VAI_PROFILE=<name>`, each VAI on the machine instead keeps its voiceprint, data and marketplace token in `local_node/profiles/<name>/` (see `profile_paths.py`). `make_questionnaire.py` and `import_answers.py` build test profiles from an offline questionnaire.

### B. Two-Sided Web Platform (`web_platform/`)
* **`config.py` (Environments):** Reads `VAI_ENV` (`dev`, `staging`, `production`) and refuses to start staging or production without their own database, secret key and node registration key. See [ENVIRONMENTS.md](ENVIRONMENTS.md).
* **`models.py` (Data Layer):** Defines `WorkerProfile` (a VAI's public card, earnings and a hash of its node token) and `MarketplaceTask` (job lifecycle states and the hired VAI). Defaults to SQLite for zero-config local development and supports PostgreSQL via `DATABASE_URL`. It never seeds or reads worker files.
* **`main.py` (Web UI & Bridge API):**
  * **Employer Side (`/employer`):** Lists registered VAIs, lets employers hire a specific VAI for a scoped task with a direct payout, and displays human-approved deliverables.
  * **Worker Side (`/worker`, `/worker/<id>`):** One accessible approval queue per VAI, where its human worker reviews, edits, approves, or declines AI-generated drafts.
  * **Bridge Endpoints (`/api/bridge/*`):** `register` accepts only a VAI's public card (unknown fields are rejected) and issues a token. `tasks`, `submit` and `outcomes` require that token and only cover tasks hired to that VAI.

---

## 4. Task Lifecycle & State Machine

Every job posted on the platform moves through a strict four-state lifecycle:

1. **`OPEN`:** Employer posts a scoped task and sets the direct worker payout.
2. **`DRAFT_READY` (or `DECLINED`):** The local VAI node pulls the task, checks boundaries, and posts a draft deliverable (or an automatic boundary decline) back to the platform.
3. **`APPROVED`:** The human worker reviews the draft on `/worker`, makes any desired edits, and clicks **Approve & Deliver**.
4. **Completed & Paid:** The approved deliverable becomes visible to the employer, and 100% of the payout is credited to the worker's balance.

---

## 5. Networking & Proxy Resilience

To ensure reliable execution across consumer Windows, macOS, and Linux environments without requiring port forwarding, inbound webhooks, or firewall changes:
* **Outbound-Only Polling:** The local node initiates all network requests outbound to the platform API.
* **Direct Socket Connections:** `worker_agent.py` uses Python's standard `http.client` rather than higher-level HTTP wrappers to prevent stale OS/registry proxy settings from blocking local or direct IP connections (`Errno 11001`).

---

## 6. Roadmap for Contributors

* **Accessible Interview Front End:** Voice and switch-access input for `interviewer.py` and `deep_interview.py` (currently terminal-based).
* **Authentication & Node Pairing:** Add cryptographic API tokens so each local VAI node authenticates securely with its corresponding `WorkerProfile`.
* **Escrow & Direct Payouts:** Integrate Stripe Connect Express accounts for automated employer-to-worker disbursements upon task approval.
