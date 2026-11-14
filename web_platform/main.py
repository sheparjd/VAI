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
        <title>{title} — Voiceprint AI</title>
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
            <h3>{w.display_name} — <span style="font-weight:normal; color:#475569;">{w.headline}</span></h3>
            <p>{w.bio_summary}</p>
            <p><strong>Total Earned: </strong>{w.total_earned}</p>
            <p><strong>Domains:</strong> {w.domains}</p>
            <p><strong>Guardrails:</strong> {w.boundaries}</p>
        </div>
        """
        for w in workers
    )

    task_cards = "".join(
        f"""
        <div class="card">
            <span class="badge {'badge-approved' if t.status == 'APPROVED' else 'badge-open'}">{t.status}</span>
            <strong style="float:right;">Payout: ${t.payout_amount:.2f}</strong>
            <h3>{t.title}</h3>
            <p>{t.description}</p>
            {f'<h4>Delivered Work (Human-Approved):</h4><pre>{t.draft_output}</pre>' if t.status == 'APPROVED' else '<p style="color:#64748b;"><em>Awaiting VAI drafting and human worker approval...</em></p>'}
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
@app.get("/worker", response_class=HTMLResponse)
def worker_portal(db: Session = Depends(get_db)):
    worker = db.query(WorkerProfile).first()
    #worker2 = db.query(WorkerProfile).second()
    tasks = db.query(MarketplaceTask).order_by(MarketplaceTask.id.desc()).all()

    task_items = ""
    for t in tasks:
        actions = ""
        if t.status in ("OPEN", "DRAFT_READY"):
            draft_val = t.draft_output or "Draft generated by local VAI node ready for your review."
            actions = f"""
            <form action="/worker/tasks/{t.id}/approve" method="post" style="margin-top:12px;">
                <label><strong>Review or Edit VAI Draft Before Delivery:</strong></label>
                <textarea name="final_output" rows="4">{draft_val}</textarea>
                <button type="submit" class="btn-green">Approve & Deliver (${t.payout_amount:.2f})</button>
            </form>
            <form action="/worker/tasks/{t.id}/decline" method="post" style="margin-top:8px;">
                <button type="submit" class="btn-red">Decline Task</button>
            </form>
            """

        task_items += f"""
        <div class="card">
            <span class="badge {'badge-approved' if t.status == 'APPROVED' else 'badge-ready'}">{t.status}</span>
            <strong style="float:right;">Payout: ${t.payout_amount:.2f}</strong>
            <h3>{t.title}</h3>
            <p>{t.description}</p>
            {f'<p><strong>Local VAI Guardrail Check:</strong> {t.ai_reasoning}</p>' if t.ai_reasoning else ''}
            {actions}
        </div>
        """

    html = f"""
    <h1>VAI Worker Control Dashboard</h1>
    <div class="card" style="border-left: 5px solid #16a34a;">
        <h2>{worker.display_name}</h2>
        <p><strong>Direct Worker Earnings:</strong> ${worker.total_earned:.2f} (100% retained by worker)</p>
        <p><strong>Active Boundaries:</strong> {worker.boundaries}</p>
    </div>

    <h2>Task & Human Approval Queue</h2>
    {task_items or "<p>No tasks in queue. Switch to the Employer Side to post a sample task!</p>"}
    """
    return render_page("Worker Dashboard", "worker", html)


@app.post("/worker/tasks/{task_id}/approve")
def approve_task(task_id: int, final_output: str = Form(...), db: Session = Depends(get_db)):
    task = db.query(MarketplaceTask).filter(MarketplaceTask.id == task_id).first()
    worker = db.query(WorkerProfile).first()
    if task and task.status != "APPROVED":
        task.status = "APPROVED"
        task.draft_output = final_output
        if worker:
            worker.total_earned += task.payout_amount
        db.commit()
    return RedirectResponse(url="/worker", status_code=303)


@app.post("/worker/tasks/{task_id}/decline")
def decline_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(MarketplaceTask).filter(MarketplaceTask.id == task_id).first()
    if task:
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


@app.post("/api/bridge/submit")
def submit_local_draft(payload: DraftSubmission, db: Session = Depends(get_db)):
    """Local worker_agent.py posts its Ollama-generated draft here for human sign-off."""
    task = db.query(MarketplaceTask).filter(MarketplaceTask.id == payload.task_id).first()
    if not task:
        return {"error": "Task not found"}
    if payload.decision == "DECLINE":
        task.status = "DECLINED"
        task.ai_reasoning = payload.reason
    else:
        task.status = "DRAFT_READY"
        task.draft_output = payload.draft_deliverable
        task.ai_reasoning = payload.reason
    db.commit()
    return {"status": "ok", "task_status": task.status}