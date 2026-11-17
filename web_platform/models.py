from datetime import datetime

from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, String, Text,
                        create_engine, inspect, text)
from sqlalchemy.orm import declarative_base, sessionmaker

from . import config

# Defaults to a local SQLite file for zero-setup development; staging and
# production must set DATABASE_URL (see config.py).
DATABASE_URL = config.DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class WorkerProfile(Base):
    """A VAI's public card. Only what the worker's node chooses to publish lives
    here; interview answers and other training data stay on the worker's machine."""
    __tablename__ = "worker_profiles"

    id = Column(Integer, primary_key=True, index=True)
    display_name = Column(String(100), nullable=False)
    headline = Column(String(200), nullable=False)
    bio_summary = Column(Text, nullable=False)
    domains = Column(Text, default="General Knowledge")
    boundaries = Column(Text, default="No live calls")
    total_earned = Column(Float, default=0.0)
    # SHA-256 of the node's bearer token; the token itself is never stored.
    node_token_hash = Column(String(64), unique=True, index=True, nullable=True)
    registered_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)


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
    # The VAI the employer hired for this task (NULL only for legacy tasks).
    worker_id = Column(Integer, ForeignKey("worker_profiles.id"), nullable=True, index=True)


def join_list(value, fallback: str) -> str:
    """Turn a list (or plain string) into display text."""
    if isinstance(value, list):
        items = [str(v).strip() for v in value if str(v).strip()]
        return "; ".join(items) if items else fallback
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


# Columns added after the first release. Until proper migrations (Alembic)
# arrive, missing columns are added in place so existing databases keep their data.
_ADDED_COLUMNS = {
    "worker_profiles": {
        "node_token_hash": "VARCHAR(64)",
        "registered_at": "TIMESTAMP",
        "last_seen_at": "TIMESTAMP",
    },
    "marketplace_tasks": {"worker_id": "INTEGER"},
}


def _add_missing_columns() -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
        if "ix_worker_profiles_node_token_hash" not in {
                i["name"] for i in inspector.get_indexes("worker_profiles")}:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_worker_profiles_node_token_hash "
                              "ON worker_profiles (node_token_hash)"))


def init_db():
    """Create or upgrade tables. Never seeds, resets or reads worker files.

    VAIs appear on the marketplace only when a worker's own node registers
    its public card over the bridge API.
    """
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    if config.IS_DEV:
        # Dev only: drop demo profiles that older versions seeded at startup
        # (they have no node, so no VAI could ever draft for them).
        db = SessionLocal()
        try:
            hired = {w for (w,) in db.query(MarketplaceTask.worker_id).distinct() if w}
            for legacy in db.query(WorkerProfile).filter(WorkerProfile.node_token_hash.is_(None)):
                if legacy.id not in hired:
                    db.delete(legacy)
            db.commit()
        finally:
            db.close()
