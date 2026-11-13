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
* **`interviewer.py` (Training Pipeline):** Conducts a self-paced, one-question-at-a-time interview via local Ollama models. Saves raw answers to `data/interview_transcript.json` and synthesizes a structured `voiceprint.json` configuration.
* **`memory_store.py` (Personal RAG):** Uses a persistent local **ChromaDB** instance (`data/chroma_db/`) to index interview Q&As alongside optional `.txt` and `.md` reference documents in `data/knowledge/`.
* **`worker_agent.py` (Autonomous Drafter):** Polls the marketplace for `OPEN` tasks, evaluates each task against `never_accept_tasks_involving` rules in `voiceprint.json`, retrieves relevant context, and drafts deliverables in the worker's authentic voice.

### B. Two-Sided Web Platform (`web_platform/`)
* **`models.py` (Data Layer):** Defines `WorkerProfile` (public skills, boundaries, earnings) and `MarketplaceTask` (job lifecycle states). Defaults to SQLite for zero-config local demos and supports PostgreSQL via `DATABASE_URL`.
* **`main.py` (Web UI & Bridge API):**
  * **Employer Side (`/employer`):** Displays verified VAI profiles, allows posting scoped tasks with direct payouts, and displays human-approved deliverables.
  * **Worker Side (`/worker`):** Provides an accessible approval queue where the human worker reviews, edits, approves, or declines AI-generated drafts.
  * **Bridge Endpoints (`/api/bridge/*`):** Exposes lightweight JSON endpoints for local worker nodes.

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

* **Vector Retrieval Integration:** Wire `VoiceprintMemoryStore.query_memory()` directly into `worker_agent.py`'s prompt builder.
* **Authentication & Node Pairing:** Add cryptographic API tokens so each local VAI node authenticates securely with its corresponding `WorkerProfile`.
* **Escrow & Direct Payouts:** Integrate Stripe Connect Express accounts for automated employer-to-worker disbursements upon task approval.
