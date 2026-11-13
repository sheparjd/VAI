import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.orm import declarative_base, sessionmaker

# Defaults to a local SQLite file for zero-setup demos; swap to Neon Postgres via DATABASE_URL in .env
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vai_marketplace.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class WorkerProfile(Base):
    __tablename__ = "worker_profiles"

    id = Column(Integer, primary_key=True, index=True)
    display_name = Column(String(100), nullable=False)
    headline = Column(String(200), nullable=False)
    bio_summary = Column(Text, nullable=False)
    domains = Column(String(300), default="General Knowledge")
    boundaries = Column(String(300), default="No live calls")
    total_earned = Column(Float, default=0.0)


class MarketplaceTask(Base):
    __tablename__ = "marketplace_tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    payout_amount = Column(Float, default=25.0)
    status = Column(String(50), default="OPEN")  # OPEN, DRAFT_READY, APPROVED, DECLINED
    draft_output = Column(Text, default="")
    ai_reasoning = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Create tables and seed a demo VAI profile if empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if db.query(WorkerProfile).count() == 0:
        demo_worker = WorkerProfile(
            display_name="Alex M. (VAI Node #01)",
            headline="Technical Writer & Root Cause Analyst",
            bio_summary="Trains a local Voiceprint AI to break down complex IT workflows into clear, structured guides.",
            domains="Technical Documentation, Data Cleanup, Process Troubleshooting",
            boundaries="No real-time video/phone calls; Human approval required before delivery",
            total_earned=0.0
        )
        db.add(demo_worker)
        db.commit()
    db.close()
