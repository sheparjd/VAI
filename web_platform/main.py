from html import escape

from fastapi import FastAPI, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from .models import SessionLocal, WorkerProfile, MarketplaceTask, init_db

app = FastAPI(title="Voiceprint AI (VAI) Two-Sided Platform")


@app.on_event("startup")
def on_startup():
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


# --- Shared Accessible HTML Layout ---
def render_page(title: str, active_tab: str, body_html: str) -> str:
    emp_style = "font-weight:bold; border-bottom:3px solid #2563eb;" if active_tab == "employer" else ""
    wrk_style = "font-weight:bold; border-bottom:3px solid #16a34a;" if active_tab == "worker" else ""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{h(title)} — Voiceprint AI</title>
        <style>
            body {{ font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 20px; background: #f8fafc; color: #0f172a; }}
            header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #cbd5e1; padding-bottom: 15px; margin-bottom: 25px; }}
            nav a {{ text-decoration: none; color: #0f172a; margin-left: 20px; padding-bottom: 5px; font-size: 1.05rem; }}
            .card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }}
            .badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 600; background: #e2e8f0; }}
            .badge-open {{ background: #dbeafe; color: #1e40af; }}
            .badge-ready {{ background: #fef3c7; color: #92400e; }}
            .badge-approved {{ background: #dcfce7; color: #166534; }}
            input, textarea {{ width: 100%; padding: 10px; margin: 8px 0 16px 0; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 1rem; box-sizing: border-box; }}
            button {{ padding: 10px 18px; border: none; border-radius: 6px; font-size: 1rem; font-weight: 600; cursor: pointer; }}
            .btn-blue {{ background: #2563eb; color: white; }}
            .btn-green {{ background: #16a34a; color: white; }}
            .btn-red {{ background: #dc2626; color: white; margin-left: 8px; }}
            pre {{ background: #f1f5f9; padding: 14px; border-radius: 6px; white-space: pre-wrap; font-family: inherit; }}
        </style>
    </head>
    <body>
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


# --- EMPLOYER SIDE ---
@app.get("/", response_class=HTMLResponse)
@app.get("/employer", response_class=HTMLResponse)
def employer_portal(db: Session = Depends(get_db)):
    workers = db.query(WorkerProfile).all()
    tasks = db.query(MarketplaceTask).order_by(MarketplaceTask.id.desc()).all()

    worker_cards = "".join(
        f"""
        <div class="card">
            <h3>{h(w.display_name)} — <span style="font-weight:normal; color:#475569;">{h(w.headline)}</span></h3>
            <p>{h(w.bio_summary)}</p>
            <p><strong>Total Earned: </strong>{h(w.total_earned)}</p>
            <p><strong>Domains:</strong> {h(w.domains)}</p>
            <p><strong>Guardrails:</strong> {h(w.boundaries)}</p>
        </div>
        """
        for w in workers
    )

    task_cards = "".join(
        f"""
        <div class="card">
            <span class="badge {'badge-approved' if t.status == 'APPROVED' else 'badge-open'}">{h(t.status)}</span>
            <strong style="float:right;">Payout: ${t.payout_amount:.2f}</strong>
            <h3>{h(t.title)}</h3>
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

    <div class="card">
        <h2>Post a New Scoped Task</h2>
        <form action="/employer/tasks" method="post">
            <label for="title">Task Title</label>
            <input id="title" name="title" placeholder="e.g., Write a 3-step customer onboarding guide" required>
            
            <label for="description">Task Details & Requirements</label>
            <textarea id="description" name="description" rows="3" placeholder="Describe the deliverable clearly..." required></textarea>
            
            <label for="payout_amount">Direct Worker Payout ($ USD)</label>
            <input id="payout_amount" name="payout_amount" type="number" step="5" value="25" required>
            
            <button type="submit" class="btn-blue">Post Task to VAI Queue</button>
        </form>
    </div>

    <h2>Posted Tasks & Deliverables</h2>
    {task_cards}
    """
    return render_page("Employer Portal", "employer", html)


@app.post("/employer/tasks")
def create_task(
    title: str = Form(...),
    description: str = Form(...),
    payout_amount: float = Form(...),
    db: Session = Depends(get_db),
):
    task = MarketplaceTask(title=title, description=description, payout_amount=payout_amount)
    db.add(task)
    db.commit()
    return RedirectResponse(url="/employer", status_code=303)


# --- WORKER / VAI SIDE ---
# Only tasks still awaiting the worker's decision can be approved or declined.
REVIEWABLE_STATUSES = ("OPEN", "DRAFT_READY")


@app.get("/worker", response_class=HTMLResponse)
def worker_portal(db: Session = Depends(get_db)):
    worker = db.query(WorkerProfile).first()
    if worker is None:
        html = """
        <h1>VAI Worker Control Dashboard</h1>
        <div class="card" role="status">
            <h2>No worker profile found</h2>
            <p>Create your voiceprint by running <code>python local_node/interviewer.py</code>,
            then restart the web platform to load your profile.</p>
        </div>
        """
        return render_page("Worker Dashboard", "worker", html)
    tasks = db.query(MarketplaceTask).order_by(MarketplaceTask.id.desc()).all()

    task_items = ""
    for t in tasks:
        actions = ""
        if t.status in REVIEWABLE_STATUSES:
            if t.status == "DRAFT_READY":
                # A real draft from the local VAI node is ready for review.
                approve_form = f"""
            <form action="/worker/tasks/{t.id}/approve" method="post" style="margin-top:12px;">
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
            <form action="/worker/tasks/{t.id}/approve" method="post" style="margin-top:12px;">
                <label for="final_output_{t.id}"><strong>Or write your own answer and deliver it:</strong></label>
                <textarea id="final_output_{t.id}" name="final_output" rows="4" required></textarea>
                <button type="submit" class="btn-green">Deliver My Answer (${t.payout_amount:.2f})</button>
            </form>"""
            actions = f"""
            {approve_form}
            <form action="/worker/tasks/{t.id}/decline" method="post" style="margin-top:8px;">
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
    <h1>VAI Worker Control Dashboard</h1>
    <div class="card" style="border-left: 5px solid #16a34a;">
        <h2>{h(worker.display_name)}</h2>
        <p><strong>Direct Worker Earnings:</strong> ${worker.total_earned:.2f} (100% retained by worker)</p>
        <p><strong>Active Boundaries:</strong> {h(worker.boundaries)}</p>
    </div>

    <h2>Task & Human Approval Queue</h2>
    {task_items or "<p>No tasks in queue. Switch to the Employer Side to post a sample task!</p>"}
    """
    return render_page("Worker Dashboard", "worker", html)


@app.post("/worker/tasks/{task_id}/approve")
def approve_task(task_id: int, final_output: str = Form(...), db: Session = Depends(get_db)):
    task = db.query(MarketplaceTask).filter(MarketplaceTask.id == task_id).first()
    worker = db.query(WorkerProfile).first()
    # A declined or already-approved task can't be approved (and paid) again,
    # and approval needs a worker to credit the payout to.
    # Never deliver (and pay for) an empty deliverable.
    if task and worker and task.status in REVIEWABLE_STATUSES and final_output.strip():
        task.status = "APPROVED"
        task.draft_output = final_output
        worker.total_earned += task.payout_amount
        db.commit()
    return RedirectResponse(url="/worker", status_code=303)


@app.post("/worker/tasks/{task_id}/decline")
def decline_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(MarketplaceTask).filter(MarketplaceTask.id == task_id).first()
    # Don't let an approved (already paid) task be flipped to DECLINED.
    if task and task.status in REVIEWABLE_STATUSES:
        task.status = "DECLINED"
        db.commit()
    return RedirectResponse(url="/worker", status_code=303)


# --- BRIDGE API (For Local VAI Node Polling) ---
class DraftSubmission(BaseModel):
    task_id: int
    decision: str
    reason: str
    draft_deliverable: str


@app.get("/api/bridge/tasks")
def poll_open_tasks(db: Session = Depends(get_db)):
    """Local worker_agent.py polls this endpoint for OPEN tasks."""
    tasks = db.query(MarketplaceTask).filter(MarketplaceTask.status == "OPEN").all()
    return [{"id": t.id, "title": t.title, "description": t.description} for t in tasks]


@app.get("/api/bridge/outcomes")
def task_outcomes(ids: str = "", db: Session = Depends(get_db)):
    """Local worker_agent.py asks how the worker resolved tasks it drafted,
    so it can learn from edits locally. Returns only finished tasks."""
    try:
        task_ids = [int(i) for i in ids.split(",") if i.strip()][:200]
    except ValueError:
        return []
    if not task_ids:
        return []
    tasks = (
        db.query(MarketplaceTask)
        .filter(MarketplaceTask.id.in_(task_ids), MarketplaceTask.status.in_(("APPROVED", "DECLINED")))
        .all()
    )
    return [
        {"id": t.id, "title": t.title, "status": t.status,
         "final_output": t.draft_output if t.status == "APPROVED" else ""}
        for t in tasks
    ]


@app.post("/api/bridge/submit")
def submit_local_draft(payload: DraftSubmission, db: Session = Depends(get_db)):
    """Local worker_agent.py posts its Ollama-generated draft here for human sign-off."""
    task = db.query(MarketplaceTask).filter(MarketplaceTask.id == payload.task_id).first()
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