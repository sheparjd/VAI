"""Local-first personal memory (RAG) for the VAI node.

Everything stays on this machine:
- Vectors are stored in a local ChromaDB folder (data/chroma_db/), with
  ChromaDB's anonymous telemetry switched off.
- Embeddings come from a small local Ollama model (default: nomic-embed-text,
  ~274 MB), so no embedding model is downloaded behind the user's back.

Memory sources:
- data/interview_transcript.json  (interview answers)
- data/knowledge/*.txt|*.md        (the worker's own reference docs / work samples)
- data/corrections.jsonl           (outcomes of AI drafts the worker reviewed)
"""
import hashlib
import json
import os
from pathlib import Path

import chromadb
import ollama
from chromadb.config import Settings

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("VAI_DATA_DIR") or BASE_DIR / "data")
TRANSCRIPT_PATH = DATA_DIR / "interview_transcript.json"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
CORRECTIONS_PATH = DATA_DIR / "corrections.jsonl"
CHROMA_PATH = DATA_DIR / "chroma_db"

EMBED_MODEL = os.getenv("VAI_EMBED_MODEL", "nomic-embed-text")
EMBED_BATCH_SIZE = 16          # keeps peak memory low on modest laptops
MAX_CHUNK_CHARS = 1500         # long paragraphs are split to this size
MAX_CONTEXT_CHARS = 4000       # cap on memory text added to a task prompt


class MemoryUnavailable(Exception):
    """The local memory store can't run (e.g. the embedding model isn't installed)."""


def _hash_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _split_text(text: str) -> list[str]:
    """Split on blank lines, then cut any very long paragraph into windows."""
    chunks = []
    for para in (p.strip() for p in text.split("\n\n")):
        while len(para) > MAX_CHUNK_CHARS:
            chunks.append(para[:MAX_CHUNK_CHARS])
            para = para[MAX_CHUNK_CHARS:]
        if para:
            chunks.append(para)
    return chunks


class VoiceprintMemoryStore:
    """Local ChromaDB vector store for the worker's interview, documents and reviewed work."""

    def __init__(self, embed_model: str = EMBED_MODEL):
        self.embed_model = embed_model
        try:
            ollama.show(embed_model)
        except Exception as e:
            raise MemoryUnavailable(
                f"embedding model '{embed_model}' isn't available in Ollama ({e}). "
                f"Run 'ollama pull {embed_model}'."
            ) from e

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(CHROMA_PATH), settings=Settings(anonymized_telemetry=False)
        )
        # One collection per embedding model, since vectors from different
        # models can't be mixed.
        slug = "".join(ch if ch.isalnum() else "_" for ch in embed_model)
        self.collection = self.client.get_or_create_collection(
            name=f"voiceprint_{slug}",
            embedding_function=None,  # we always pass embeddings from Ollama
            metadata={"hnsw:space": "cosine"},
        )

    # --- Embedding -------------------------------------------------------
    def _embed(self, texts: list[str], kind: str) -> list[list[float]]:
        # nomic-embed-text expects task prefixes; other models ignore them harmlessly.
        prefix = "search_query: " if kind == "query" else "search_document: "
        vectors = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = [prefix + t for t in texts[i:i + EMBED_BATCH_SIZE]]
            vectors.extend(ollama.embed(model=self.embed_model, input=batch)["embeddings"])
        return vectors

    # --- Sources ---------------------------------------------------------
    def _transcript_entries(self) -> dict:
        if not TRANSCRIPT_PATH.exists():
            return {}
        with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
            transcript = json.load(f) or []
        entries = {}
        for item in transcript:
            doc = f"Interview question: {item['question']}\nWorker's answer: {item['answer']}"
            entries[_hash_id("qa", doc)] = (doc, {"source": "interview"})
        return entries

    def _knowledge_entries(self) -> dict:
        entries = {}
        files = sorted(KNOWLEDGE_DIR.glob("*.txt")) + sorted(KNOWLEDGE_DIR.glob("*.md"))
        for file_path in files:
            content = file_path.read_text(encoding="utf-8", errors="replace").strip()
            for chunk in _split_text(content):
                entries[_hash_id("doc", file_path.name, chunk)] = (
                    chunk, {"source": f"knowledge/{file_path.name}"}
                )
        return entries

    def _correction_entries(self) -> dict:
        if not CORRECTIONS_PATH.exists():
            return {}
        entries = {}
        with open(CORRECTIONS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                task = f"Task: {rec['title']}\n{rec['description']}"
                if rec["outcome"] == "APPROVED":
                    doc = f"{task}\nWorker's approved final answer:\n{rec['final_output']}"
                    meta = {"source": "approved_work", "edited": bool(rec.get("edited"))}
                elif rec["outcome"] == "DECLINED":
                    doc = f"The worker declined this task after reviewing the AI draft.\n{task}"
                    meta = {"source": "declined_task"}
                else:
                    continue  # DISCARDED records aren't learned from
                for chunk in _split_text(doc)[:3]:  # cap very long answers
                    entries[_hash_id("fix", str(rec["task_id"]), chunk)] = (chunk, meta)
        return entries

    # --- Sync & query ----------------------------------------------------
    def sync_all(self) -> dict:
        """Bring the vector store in line with the source files.

        Entries are keyed by a hash of their content, so only new or changed
        text is embedded, and removed text is deleted.
        """
        sources = {
            "interview": self._transcript_entries(),
            "knowledge": self._knowledge_entries(),
            "reviewed_work": self._correction_entries(),
        }
        desired = {k: v for entries in sources.values() for k, v in entries.items()}
        existing = set(self.collection.get(include=[])["ids"])

        stale = list(existing - desired.keys())
        if stale:
            self.collection.delete(ids=stale)

        new_ids = [i for i in desired if i not in existing]
        if new_ids:
            docs = [desired[i][0] for i in new_ids]
            self.collection.add(
                ids=new_ids,
                documents=docs,
                metadatas=[desired[i][1] for i in new_ids],
                embeddings=self._embed(docs, kind="document"),
            )

        stats = {name: len(entries) for name, entries in sources.items()}
        stats.update(added=len(new_ids), removed=len(stale))
        return stats

    def query_memory(self, query_text: str, n_results: int = 5) -> str:
        """Return the most relevant memory snippets for a task, as prompt text."""
        total = self.collection.count()
        if total == 0:
            return ""
        results = self.collection.query(
            query_embeddings=self._embed([query_text], kind="query"),
            n_results=min(n_results, total),
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        if not docs:
            return ""

        lines = ["Relevant memory from the worker (interview answers, their documents, and work they approved):"]
        used = 0
        for doc, meta in zip(docs, metas):
            if used + len(doc) > MAX_CONTEXT_CHARS:
                break
            lines.append(f"--- [{(meta or {}).get('source', 'memory')}]\n{doc}")
            used += len(doc)
        return "\n".join(lines)


if __name__ == "__main__":
    store = VoiceprintMemoryStore()
    stats = store.sync_all()
    print(f"Memory sync complete: {stats}")

    sample = store.query_memory("How do you approach solving technical problems?")
    if sample:
        print("\nSample Retrieval Test:\n" + sample)
    else:
        print("\nMemory store is empty. Run interviewer.py or add .txt/.md files to local_node/data/knowledge/.")
