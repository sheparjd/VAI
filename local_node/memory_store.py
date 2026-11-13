import json
from pathlib import Path
import chromadb

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TRANSCRIPT_PATH = DATA_DIR / "interview_transcript.json"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
CHROMA_PATH = DATA_DIR / "chroma_db"


class VoiceprintMemoryStore:
    """Local-first ChromaDB vector store for personal interview transcripts and reference docs."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        self.collection = self.client.get_or_create_collection(name="voiceprint_memory")

    def index_transcript(self) -> int:
        """Load interview_transcript.json and upsert Q&A pairs into ChromaDB."""
        if not TRANSCRIPT_PATH.exists():
            print(f"[Info] No transcript found at {TRANSCRIPT_PATH} yet.")
            return 0

        with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
            transcript = json.load(f)

        if not transcript:
            return 0

        documents = []
        metadatas = []
        ids = []

        for idx, item in enumerate(transcript):
            doc_text = f"Question: {item['question']}\nWorker Answer: {item['answer']}"
            documents.append(doc_text)
            metadatas.append({
                "source": "interview_transcript",
                "timestamp": item.get("timestamp", "")
            })
            ids.append(f"interview_qa_{idx}")

        self.collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
        return len(documents)

    def index_knowledge_docs(self) -> int:
        """Index any optional .txt or .md files placed in local_node/data/knowledge/."""
        files = list(KNOWLEDGE_DIR.glob("*.txt")) + list(KNOWLEDGE_DIR.glob("*.md"))
        if not files:
            return 0

        documents = []
        metadatas = []
        ids = []

        for file_path in files:
            content = file_path.read_text(encoding="utf-8").strip()
            if not content:
                continue

            # Split into simple paragraph chunks so retrieval stays focused
            chunks = [c.strip() for c in content.split("\n\n") if c.strip()]
            for chunk_idx, chunk in enumerate(chunks):
                documents.append(chunk)
                metadatas.append({"source": file_path.name, "chunk": chunk_idx})
                ids.append(f"doc_{file_path.stem}_{chunk_idx}")

        if documents:
            self.collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
        return len(documents)

    def sync_all(self) -> dict:
        """Refresh the local vector store from both interview transcripts and knowledge files."""
        qa_count = self.index_transcript()
        doc_count = self.index_knowledge_docs()
        return {"interview_entries": qa_count, "knowledge_chunks": doc_count}

    def query_memory(self, query_text: str, n_results: int = 3) -> str:
        """Retrieve the most relevant personal memory snippets for a given task description."""
        total_items = self.collection.count()
        if total_items == 0:
            return ""

        limit = min(n_results, total_items)
        results = self.collection.query(query_texts=[query_text], n_results=limit)
        docs = results.get("documents", [[]])[0]

        if not docs:
            return ""

        formatted = ["Relevant Personal Knowledge & Style Examples:"]
        for doc in docs:
            formatted.append(f"---\n{doc}")
        return "\n".join(formatted)


if __name__ == "__main__":
    store = VoiceprintMemoryStore()
    stats = store.sync_all()
    print(f"Memory sync complete: {stats['interview_entries']} interview Q&As, {stats['knowledge_chunks']} doc chunks indexed.")

    sample = store.query_memory("How do you approach solving technical problems?")
    if sample:
        print("\nSample Retrieval Test:\n" + sample)
    else:
        print("\nMemory store is empty. Run interviewer.py or add .txt/.md files to local_node/data/knowledge/.")
