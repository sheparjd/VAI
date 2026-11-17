import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from html import escape
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from . import config
from .models import MarketplaceTask, SessionLocal, WorkerProfile, init_db, join_list

app = FastAPI(title="Voiceprint AI (VAI) Two-Sided Platform")

NODE_ONLINE_WINDOW = timedelta(seconds=60)  # nodes poll every few seconds


@app.on_event("startup")
def on_startup():
    config.check_settings()
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def h(value) -> str:
    """Escape any user-, employer- or LLM-supplied value before putting it in HTML."""
    return escape("" if value is None else str(value), quote=True)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def node_online(worker: WorkerProfile) -> bool:
    return bool(worker.last_seen_at and datetime.utcnow() - worker.last_seen_at < NODE_ONLINE_WINDOW)


# --- Shared Accessible HTML Layout ---
ENV_BANNERS = {
    "dev": ("#fef3c7", "#92400e", "DEV environment: local testing only. Data here is disposable."),
    "staging": ("#ede9fe", "#5b21b6", "STAGING environment: test VAIs and [TEST] tasks only. No real payments."),
}


def render_page(title: str, active_tab: str, body_html: str) -> str:
    emp_style = "font-weight:bold; border-bottom:3px solid #2563eb;" if active_tab == "employer" else ""
    wrk_style = "font-weight:bold; border-bottom:3px solid #16a34a;" if active_tab == "worker" else ""
    banner = ""
    if config.VAI_ENV in ENV_BANNERS:
        bg, fg, msg = ENV_BANNERS[config.VAI_ENV]
        banner = f'<div role="note" style="background:{bg}; color:{fg}; padding:8px 14px; border-radius:6px; margin-bottom:16px; font-weight:600;">{h(msg)}</div>'
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{h(title)} — Voiceprint AI</title>
        <style>
            body {{ font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 20px; background: #f8fafc; color: #0f172a; }}
            header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #cbd5e1; padding-bottom: 15px; margin-bottom: 25px; flex-wrap: wrap; gap: 8px; }}
            nav a {{ text-decoration: none; color: #0f172a; margin-left: 20px; padding-bottom: 5px; font-size: 1.05rem; }}
            .card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }}
            .badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 600; background: #e2e8f0; }}
            .badge-open {{ background: #dbeafe; color: #1e40af; }}
            .badge-ready {{ background: #fef3c7; color: #92400e; }}
            .badge-approved {{ background: #dcfce7; color: #166534; }}
            .badge-online {{ background: #dcfce7; color: #166534; }}
            .badge-offline {{ background: #f1f5f9; color: #475569; }}
            input, textarea, select {{ width: 100%; padding: 10px; margin: 8px 0 16px 0; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 1rem; box-sizing: border-box; }}
            button, .btn {{ padding: 10px 18px; border: none; border-radius: 6px; font-size: 1rem; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }}
            .btn-blue {{ background: #2563eb; color: white; }}
            .btn-green {{ background: #16a34a; color: white; }}
            .btn-red {{ background: #dc2626; color: white; margin-left: 8px; }}
            pre {{ background: #f1f5f9; padding: 14px; border-radius: 6px; white-space: pre-wrap; font-family: inherit; }}
        </style>
    </head>
    <body>
        {banner}
        <header>
            <div><strong>Voiceprint AI (VAI)</strong> <span style="color:#64748b;">| Decentralized Human-Owned AI Labor</span></div>
            <nav>
                <a href="/employer" style="{emp_style}">Employer Side</a>
                <a href="/worker" style="{wrk_style}">VAI / Worker Side</a>
            </nav>
        </header>
        {body_html}
    </body>
    </html>
    """


def status_badge(worker: WorkerProfile) -> str:
    if node_online(worker):
        return '<span class="badge badge-online">Node online</span>'
    return '<span class="badge badge-offline">Node offline</span>'


# --- EMPLOYER SIDE ---
@app.get("/", response_class=HTMLResponse)
@app.get("/employer", response_class=HTMLResponse)
def employer_portal(vai: int | None = None, db: Session = Depends(get_db)):
    workers = db.query(WorkerProfile).filter(WorkerProfile.node_token_hash.isnot(None)) \
        .order_by(WorkerProfile.display_name).all()
    names = {w.id: w.display_name for w in db.query(WorkerProfile).all()}
    tasks = db.query(MarketplaceTask).order_by(MarketplaceTask.id.desc()).all()

    worker_cards = "".join(
        f"""
        <div class="card">
            {status_badge(w)}
            <h3>{h(w.display_name)} — <span style="font-weight:normal; color:#475569;">{h(w.headline)}</span></h3>
            <p>{h(w.bio_summary)}</p>
            <p><strong>Domains:</strong> {h(w.domains)}</p>
            <p><strong>Guardrails:</strong> {h(w.boundaries)}</p>
            <a class="btn btn-blue" href="/employer?vai={w.id}#post-task">Hire {h(w.display_name)}</a>
        </div>
        """
        for w in workers
    ) or """<div class="card" role="status"><p>No VAIs have registered yet. A VAI appears here
    when its worker starts <code>python local_node/worker_agent.py</code>.</p></div>"""

    options = "".join(
        f'<option value="{w.id}"{" selected" if w.id == vai else ""}>{h(w.display_name)} — {h(w.headline)}</option>'
        for w in workers
    )
    task_form = f"""
    <div class="card" id="post-task">
        <h2>Post a New Scoped Task</h2>
        <form action="/employer/tasks" method="post">
            <label for="worker_id">Hire this VAI</label>
            <select id="worker_id" name="worker_id" required>
                <option value="">Choose a VAI…</option>
                {options}
            </select>

            <label for="title">Task Title</label>
            <input id="title" name="title" placeholder="e.g., Write a 3-step customer onboarding guide" required>

            <label for="description">Task Details & Requirements</label>
            <textarea id="description" name="description" rows="3" placeholder="Describe the deliverable clearly..." required></textarea>

            <label for="payout_amount">Direct Worker Payout ($ USD)</label>
            <input id="payout_amount" name="payout_amount" type="number" step="5" min="1" value="25" required>

            <button type="submit" class="btn-blue">Post Task to This VAI</button>
        </form>
    </div>""" if workers else ""

    def assignee(t):
        if t.worker_id is None:
            return "Unassigned (posted before VAIs could be chosen)"
        return names.get(t.worker_id, "Removed VAI")

    task_cards = "".join(
        f"""
        <div class="card">
            <span class="badge {'badge-approved' if t.status == 'APPROVED' else 'badge-open'}">{h(t.status)}</span>
            <strong style="float:right;">Payout: ${t.payout_amount:.2f}</strong>
            <h3>{h(t.title)}</h3>
            <p style="color:#475569;">Hired VAI: <strong>{h(assignee(t))}</strong></p>
            <p>{h(t.description)}</p>
            {f'<h4>Delivered Work (Human-Approved):</h4><pre>{h(t.draft_output)}</pre>' if t.status == 'APPROVED' else '<p style="color:#64748b;"><em>Awaiting VAI drafting and human worker approval...</em></p>'}
        </div>
        """
        for t in tasks
    ) or "<p>No tasks posted yet.</p>"

    html = f"""
    <h1>Employer Marketplace</h1>
    <h2>Available VAI Representatives</h2>
    {worker_cards}
    {task_form}
    <h2>Posted Tasks & Deliverables</h2>
    {task_cards}
    """
    return render_page("Employer Portal", "employer", html)


@app.post("/employer/tasks")
def create_task(
    worker_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    payout_amount: float = Form(...),
    db: Session = Depends(get_db),
):
    worker = db.query(WorkerProfile).filter(WorkerProfile.id == worker_id,
                                            WorkerProfile.node_token_hash.isnot(None)).first()
    if worker and title.strip() and description.strip() and payout_amount > 0:
        db.add(MarketplaceTask(title=title, description=description,
                               payout_amount=payout_amount, worker_id=worker.id))
        db.commit()
    return RedirectResponse(url="/employer", status_code=303)


# --- WORKER / VAI SIDE ---
# Only tasks still awaiting the worker's decision can be approved or declined.
REVIEWABLE_STATUSES = ("OPEN", "DRAFT_READY")
# TODO before production: worker logins. Until then anyone who can reach the
# platform can open any worker's dashboard, which is acceptable only in dev/staging.


@app.get("/worker", response_class=HTMLResponse)
def worker_index(db: Session = Depends(get_db)):
    workers = db.query(WorkerProfile).filter(WorkerProfile.node_token_hash.isnot(None)) \
        .order_by(WorkerProfile.display_name).all()
    if not workers:
        html = """
        <h1>VAI Worker Control Dashboard</h1>
        <div class="card" role="status">
            <h2>No VAIs registered yet</h2>
            <p>Create your voiceprint with <code>python local_node/interviewer.py</code>, then start
            <code>python local_node/worker_agent.py</code>. Your node registers your public card here;
            your interview answers stay on your machine.</p>
        </div>
        """
        return render_page("Worker Dashboard", "worker", html)
    items = "".join(
        f"""<li class="card" style="list-style:none;">{status_badge(w)}
        <h3 style="margin:6px 0;"><a href="/worker/{w.id}">{h(w.display_name)}</a></h3>
        <p style="margin:0; color:#475569;">{h(w.headline)}</p></li>"""
        for w in workers
    )
    html = f"""
    <h1>VAI Worker Control Dashboards</h1>
    <p>Choose your VAI to review its drafts.</p>
    <ul style="padding:0;">{items}</ul>
    """
    return render_page("Worker Dashboards", "worker", html)


def _get_worker(db: Session, worker_id: int) -> WorkerProfile | None:
    return db.query(WorkerProfile).filter(WorkerProfile.id == worker_id,
                                          WorkerProfile.node_token_hash.isnot(None)).first()


@app.get("/worker/{worker_id}", response_class=HTMLResponse)
def worker_portal(worker_id: int, db: Session = Depends(get_db)):
    worker = _get_worker(db, worker_id)
    if worker is None:
        return RedirectResponse(url="/worker", status_code=303)
    tasks = db.query(MarketplaceTask).filter(MarketplaceTask.worker_id == worker.id) \
        .order_by(MarketplaceTask.id.desc()).all()

    task_items = ""
    for t in tasks:
        actions = ""
        base = f"/worker/{worker.id}/tasks/{t.id}"
        if t.status in REVIEWABLE_STATUSES:
            if t.status == "DRAFT_READY":
                # A real draft from the local VAI node is ready for review.
                approve_form = f"""
            <form action="{base}/approve" method="post" style="margin-top:12px;">
                <label for="final_output_{t.id}"><strong>Review or Edit VAI Draft Before Delivery:</strong></label>
                <textarea id="final_output_{t.id}" name="final_output" rows="8" required>{h(t.draft_output)}</textarea>
                <button type="submit" class="btn-green">Approve & Deliver (${t.payout_amount:.2f})</button>
            </form>"""
            else:
                # OPEN: no AI draft yet. Never pre-fill a fake draft; the worker
                # can wait for their VAI node or write the answer themselves.
                approve_form = f"""
            <p role="status" style="color:#64748b;"><em>Waiting for your local VAI node to draft this task.
            Make sure <code>python local_node/worker_agent.py</code> is running.</em></p>
            <form action="{base}/approve" method="post" style="margin-top:12px;">
                <label for="final_output_{t.id}"><strong>Or write your own answer and deliver it:</strong></label>
                <textarea id="final_output_{t.id}" name="final_output" rows="4" required></textarea>
                <button type="submit" class="btn-green">Deliver My Answer (${t.payout_amount:.2f})</button>
            </form>"""
            actions = f"""
            {approve_form}
            <form action="{base}/decline" method="post" style="margin-top:8px;">
                <button type="submit" class="btn-red">Decline Task</button>
            </form>
            """

        task_items += f"""
        <div class="card">
            <span class="badge {'badge-approved' if t.status == 'APPROVED' else 'badge-ready'}">{h(t.status)}</span>
            <strong style="float:right;">Payout: ${t.payout_amount:.2f}</strong>
            <h3>{h(t.title)}</h3>
            <p>{h(t.description)}</p>
            {f'<p><strong>Local VAI Check (expertise &amp; guardrails):</strong> {h(t.ai_reasoning)}</p>' if t.ai_reasoning else ''}
            {actions}
        </div>
        """

    html = f"""
    <p><a href="/worker">&larr; All VAIs</a></p>
    <h1>VAI Worker Control Dashboard</h1>
    <div class="card" style="border-left: 5px solid #16a34a;">
        {status_badge(worker)}
        <h2>{h(worker.display_name)}</h2>
        <p><strong>Direct Worker Earnings:</strong> ${worker.total_earned:.2f} (100% retained by worker)</p>
        <p><strong>Active Boundaries:</strong> {h(worker.boundaries)}</p>
    </div>

    <h2>Task & Human Approval Queue</h2>
    {task_items or "<p>No tasks yet. Employers can hire this VAI from the Employer Side.</p>"}
    """
    return render_page("Worker Dashboard", "worker", html)


def _worker_task(db: Session, worker_id: int, task_id: int) -> MarketplaceTask | None:
    return db.query(MarketplaceTask).filter(MarketplaceTask.id == task_id,
                                            MarketplaceTask.worker_id == worker_id).first()


@app.post("/worker/{worker_id}/tasks/{task_id}/approve")
def approve_task(worker_id: int, task_id: int, final_output: str = Form(...), db: Session = Depends(get_db)):
    worker = _get_worker(db, worker_id)
    task = _worker_task(db, worker_id, task_id) if worker else None
    # A declined or already-approved task can't be approved (and paid) again,
    # a task can only be approved on its own VAI's dashboard (which gets the payout),
    # and an empty deliverable is never delivered (or paid for).
    if task and task.status in REVIEWABLE_STATUSES and final_output.strip():
        task.status = "APPROVED"
        task.draft_output = final_output
        worker.total_earned += task.payout_amount
        db.commit()
    return RedirectResponse(url=f"/worker/{worker_id}", status_code=303)


@app.post("/worker/{worker_id}/tasks/{task_id}/decline")
def decline_task(worker_id: int, task_id: int, db: Session = Depends(get_db)):
    task = _worker_task(db, worker_id, task_id)
    # Don't let an approved (already paid) task be flipped to DECLINED.
    if task and task.status in REVIEWABLE_STATUSES:
        task.status = "DECLINED"
        db.commit()
    return RedirectResponse(url=f"/worker/{worker_id}", status_code=303)


# --- BRIDGE API (For Local VAI Node Polling) ---
# Each node authenticates with its own bearer token and only ever sees the
# tasks hired to its VAI.
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PublicCard(BaseModel):
    """Everything the platform accepts about a VAI. Unknown fields are rejected,
    so a node can't accidentally upload interview answers or other private data."""
    model_config = ConfigDict(extra="forbid")

    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    headline: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    bio_summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""
    domains: list[ShortText] = Field(default_factory=list, max_length=20)
    boundaries: list[ShortText] = Field(default_factory=list, max_length=20)


class DraftSubmission(BaseModel):
    task_id: int
    decision: str
    reason: str
    draft_deliverable: str


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def current_node(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> WorkerProfile:
    token = _bearer_token(authorization)
    worker = None
    if token:
        worker = db.query(WorkerProfile).filter(WorkerProfile.node_token_hash == hash_token(token)).first()
    if worker is None:
        raise HTTPException(status_code=401, detail="Unknown or missing node token.")
    return worker


def _apply_card(worker: WorkerProfile, card: PublicCard) -> None:
    worker.display_name = card.display_name
    worker.headline = card.headline
    worker.bio_summary = card.bio_summary
    worker.domains = join_list(card.domains, "General Knowledge")
    worker.boundaries = join_list(card.boundaries, "No boundaries specified")


@app.post("/api/bridge/register")
def register_node(
    card: PublicCard,
    authorization: str | None = Header(default=None),
    x_vai_registration_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """A node publishes (or refreshes) its VAI's public card.

    With a valid token: updates that VAI's card. Without one: registers a new VAI
    (requiring VAI_REGISTRATION_KEY when the platform has one) and returns its
    token exactly once; only a hash of it is stored.
    """
    token = _bearer_token(authorization)
    if token:
        worker = db.query(WorkerProfile).filter(WorkerProfile.node_token_hash == hash_token(token)).first()
        if worker is None:
            raise HTTPException(status_code=401, detail="Unknown node token.")
        _apply_card(worker, card)
        worker.last_seen_at = datetime.utcnow()
        db.commit()
        return {"vai_id": worker.id}

    if config.REGISTRATION_KEY and not hmac.compare_digest(
            (x_vai_registration_key or "").encode(), config.REGISTRATION_KEY.encode()):
        raise HTTPException(status_code=403, detail="Registration key required.")
    token = secrets.token_urlsafe(32)
    worker = WorkerProfile(display_name=card.display_name, headline=card.headline, bio_summary=card.bio_summary,
                           total_earned=0.0, node_token_hash=hash_token(token),
                           registered_at=datetime.utcnow(), last_seen_at=datetime.utcnow())
    _apply_card(worker, card)
    db.add(worker)
    db.commit()
    return {"vai_id": worker.id, "token": token}


@app.get("/api/bridge/tasks")
def poll_open_tasks(worker: WorkerProfile = Depends(current_node), db: Session = Depends(get_db)):
    """Local worker_agent.py polls this endpoint for OPEN tasks hired to its VAI."""
    worker.last_seen_at = datetime.utcnow()
    db.commit()
    tasks = db.query(MarketplaceTask).filter(MarketplaceTask.status == "OPEN",
                                             MarketplaceTask.worker_id == worker.id).all()
    return [{"id": t.id, "title": t.title, "description": t.description} for t in tasks]


@app.get("/api/bridge/outcomes")
def task_outcomes(ids: str = "", worker: WorkerProfile = Depends(current_node), db: Session = Depends(get_db)):
    """Local worker_agent.py asks how the worker resolved tasks it drafted,
    so it can learn from edits locally. Returns only this VAI's finished tasks."""
    try:
        task_ids = [int(i) for i in ids.split(",") if i.strip()][:200]
    except ValueError:
        return []
    if not task_ids:
        return []
    tasks = (
        db.query(MarketplaceTask)
        .filter(MarketplaceTask.id.in_(task_ids), MarketplaceTask.worker_id == worker.id,
                MarketplaceTask.status.in_(("APPROVED", "DECLINED")))
        .all()
    )
    return [
        {"id": t.id, "title": t.title, "status": t.status,
         "final_output": t.draft_output if t.status == "APPROVED" else ""}
        for t in tasks
    ]


@app.post("/api/bridge/submit")
def submit_local_draft(payload: DraftSubmission, worker: WorkerProfile = Depends(current_node),
                       db: Session = Depends(get_db)):
    """Local worker_agent.py posts its Ollama-generated draft here for human sign-off."""
    task = _worker_task(db, worker.id, payload.task_id)
    if not task:
        return {"error": "Task not found"}
    # The worker may have answered or declined the task while the AI was
    # drafting; never overwrite their decision with a late AI submission.
    if task.status != "OPEN":
        return {"status": "ignored", "task_status": task.status}
    if payload.decision == "DECLINE":
        task.status = "DECLINED"
        task.ai_reasoning = payload.reason
    else:
        task.status = "DRAFT_READY"
        task.draft_output = payload.draft_deliverable
        task.ai_reasoning = payload.reason
    db.commit()
    return {"status": "ok", "task_status": task.status}
