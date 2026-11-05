"""Vector indexer using TF-IDF and Cosine similarity for deterministic knowledge search."""
from pathlib import Path
from typing import List, Tuple
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from contracts.schemas import RetrievedDocument


class PolicyVectorIndexer:
    """Builds and persists TF-IDF vector index for policy retrieval."""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        self.documents: List[RetrievedDocument] = []
        self.doc_matrix = None

    def fit_and_save(self, documents: List[RetrievedDocument], persist_path: Path) -> None:
        """Fit vectorizer on policy texts and save index to disk."""
        persist_path = Path(persist_path)
        self.documents = documents
        corpus = [
            f"{doc.title} {' '.join(getattr(doc, 'tags', []))} {doc.content}".strip()
            for doc in documents
        ]
        self.doc_matrix = self.vectorizer.fit_transform(corpus)

        persist_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "vectorizer": self.vectorizer,
                "documents": self.documents,
                "doc_matrix": self.doc_matrix,
            },
            persist_path,
        )

    def load(self, persist_path: Path) -> None:
        """Load index artifact from disk."""
        persist_path = Path(persist_path)
        if not persist_path.exists():
            raise FileNotFoundError(f"Vector index artifact not found at {persist_path}")
        data = joblib.load(persist_path)
        self.vectorizer = data["vectorizer"]
        self.documents = data["documents"]
        self.doc_matrix = data["doc_matrix"]

    def search(self, query: str, top_k: int = 3) -> List[Tuple[RetrievedDocument, float]]:
        """Search top-k most similar policy documents using cosine similarity."""
        if self.doc_matrix is None or not self.documents:
            return []
        q_vec = self.vectorizer.transform([query])
        similarities = cosine_similarity(q_vec, self.doc_matrix)[0]

        ranked_indices = similarities.argsort()[::-1][:top_k]
        results = []
        for idx in ranked_indices:
            score = float(similarities[idx])
            doc = self.documents[idx]
            # Copy with updated score
            results.append((doc.model_copy(update={"score": round(score, 4)}), score))
        return results
