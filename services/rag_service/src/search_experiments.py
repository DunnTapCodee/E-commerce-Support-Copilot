"""Comparable policy searchers for Module 2 retrieval experiments.

All searchers use the same active-policy corpus and ``title + content`` text by
default. Optional tags can be enabled as an explicit ablation, not silently
included in only some retrieval methods.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


ORDER_ID_RE = re.compile(r"\bORD-[A-Z0-9-]+\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")


@dataclass(frozen=True)
class PolicyDocument:
    doc_id: str
    category: str
    title: str
    content: str
    version: str
    is_active: bool
    tags: tuple[str, ...] = ()

    def text(self, include_tags: bool = False) -> str:
        parts = [self.title, self.content]
        if include_tags and self.tags:
            parts.append(" ".join(self.tags))
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True)
class SearchHit:
    document: PolicyDocument
    score: float


def load_policy_documents(path, active_only: bool = True) -> list[PolicyDocument]:
    """Read the repository's root-array policies.json format."""
    import json
    from pathlib import Path

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("policies.json must contain a JSON array")

    documents = [
        PolicyDocument(
            doc_id=item["doc_id"],
            category=item.get("category", ""),
            title=item["title"],
            content=item["content"],
            version=str(item.get("version", "1.0")),
            is_active=bool(item.get("is_active", True)),
            tags=tuple(item.get("tags", [])),
        )
        for item in payload
    ]
    if active_only:
        documents = [document for document in documents if document.is_active]
    return documents


def normalize_query(query: str) -> str:
    """Remove order IDs that are not policy terms while preserving other numbers."""
    return ORDER_ID_RE.sub(" ", query).strip()


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(normalize_query(text).lower())


class TfidfSearcher:
    """The current indexer.py TF-IDF + cosine baseline (same vectorizer settings)."""

    name = "tfidf"

    def __init__(self, documents: Sequence[PolicyDocument], include_tags: bool = False):
        started = time.perf_counter()
        self.documents = [document for document in documents if document.is_active]
        self.include_tags = include_tags
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform(
            [document.text(include_tags) for document in self.documents]
        )
        self.build_ms = (time.perf_counter() - started) * 1000

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        query_vector = self.vectorizer.transform([normalize_query(query)])
        scores = cosine_similarity(query_vector, self.matrix)[0]
        return _hits(self.documents, scores, top_k, require_positive=True)


class BM25Searcher:
    """BM25Okapi lexical search with identical corpus text and metadata filtering."""

    name = "bm25"

    def __init__(self, documents: Sequence[PolicyDocument], include_tags: bool = False):
        started = time.perf_counter()
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise RuntimeError(
                "BM25 requires rank_bm25. Install requirements-retrieval-experiments.txt."
            ) from exc

        self.documents = [document for document in documents if document.is_active]
        self.include_tags = include_tags
        self.tokenized_corpus = [
            tokenize(document.text(include_tags)) for document in self.documents
        ]
        self.model = BM25Okapi(self.tokenized_corpus)
        self.document_tokens = [set(tokens) for tokens in self.tokenized_corpus]
        self.build_ms = (time.perf_counter() - started) * 1000

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = self.model.get_scores(query_tokens)
        # BM25Okapi can assign negative IDF scores to very common terms; keep
        # overlapping documents and rank by score instead of discarding them.
        matching = [
            index for index, tokens in enumerate(self.document_tokens)
            if tokens.intersection(query_tokens)
        ]
        return _hits(self.documents, scores, top_k, indices=matching)


class DenseSearcher:
    """Dense embedding retrieval, using FAISS exact IP when available.

    Embeddings are L2-normalized, so inner product is cosine similarity. For the
    47-document corpus, NumPy exact search is a dependency-free fallback.
    """

    name = "dense"

    def __init__(
        self,
        documents: Sequence[PolicyDocument],
        model_name: str = "keepitreal/vietnamese-sbert",
        include_tags: bool = False,
        device: str = "cpu",
    ):
        started = time.perf_counter()
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Dense search requires sentence-transformers. Install requirements-retrieval-experiments.txt."
            ) from exc

        self.documents = [document for document in documents if document.is_active]
        self.include_tags = include_tags
        self.model_name = model_name
        self.encoder = SentenceTransformer(model_name, device=device)
        self.embeddings = np.asarray(
            self.encoder.encode(
                [document.text(include_tags) for document in self.documents],
                batch_size=32,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
            dtype=np.float32,
        )
        self.backend = "numpy-exact"
        self.index = None
        try:
            import faiss

            self.index = faiss.IndexFlatIP(self.embeddings.shape[1])
            self.index.add(np.ascontiguousarray(self.embeddings))
            self.backend = "faiss.IndexFlatIP"
        except (ImportError, OSError):
            # FAISS wheels are not available on every platform; exact matrix
            # multiplication is more than sufficient for this small corpus.
            self.index = None
        self.build_ms = (time.perf_counter() - started) * 1000

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        query_embedding = np.asarray(
            self.encoder.encode(
                [normalize_query(query)],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
            dtype=np.float32,
        )
        if self.index is not None:
            scores, indices = self.index.search(query_embedding, min(top_k, len(self.documents)))
            return [
                SearchHit(self.documents[int(index)], float(score))
                for score, index in zip(scores[0], indices[0])
                if int(index) >= 0
            ]
        scores = self.embeddings @ query_embedding[0]
        return _hits(self.documents, scores, top_k)


def reciprocal_rank_fusion(
    ranked_lists: Iterable[Sequence[SearchHit]],
    top_k: int,
    rrf_constant: int = 60,
) -> list[SearchHit]:
    """Fuse ranked lists without requiring their raw scores to be calibrated."""
    score_by_id: dict[str, float] = {}
    document_by_id: dict[str, PolicyDocument] = {}
    for ranked_list in ranked_lists:
        for rank, hit in enumerate(ranked_list, start=1):
            doc_id = hit.document.doc_id
            score_by_id[doc_id] = score_by_id.get(doc_id, 0.0) + 1.0 / (rrf_constant + rank)
            document_by_id[doc_id] = hit.document
    ordered = sorted(score_by_id, key=lambda doc_id: (-score_by_id[doc_id], doc_id))
    return [
        SearchHit(document_by_id[doc_id], score_by_id[doc_id])
        for doc_id in ordered[:top_k]
    ]


class HybridSearcher:
    """BM25 + dense search fused with Reciprocal Rank Fusion."""

    name = "hybrid_rrf"

    def __init__(
        self,
        bm25_searcher: BM25Searcher,
        dense_searcher: DenseSearcher,
        candidate_k: int = 10,
        rrf_constant: int = 60,
    ):
        self.bm25_searcher = bm25_searcher
        self.dense_searcher = dense_searcher
        self.candidate_k = candidate_k
        self.rrf_constant = rrf_constant
        self.build_ms = bm25_searcher.build_ms + dense_searcher.build_ms

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        candidates = max(self.candidate_k, top_k)
        return reciprocal_rank_fusion(
            [
                self.bm25_searcher.search(query, candidates),
                self.dense_searcher.search(query, candidates),
            ],
            top_k=top_k,
            rrf_constant=self.rrf_constant,
        )


class RerankedHybridSearcher:
    """Cross-encode the RRF candidate set and return the final top-k."""

    name = "hybrid_rrf_reranked"

    def __init__(
        self,
        hybrid_searcher: HybridSearcher,
        model_name: str = "BAAI/bge-reranker-base",
        candidate_k: int = 10,
        device: str = "cpu",
    ):
        started = time.perf_counter()
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "Cross-encoder reranking requires sentence-transformers."
            ) from exc
        self.hybrid_searcher = hybrid_searcher
        self.candidate_k = candidate_k
        self.model_name = model_name
        self.reranker = CrossEncoder(model_name, device=device, max_length=512)
        self.build_ms = hybrid_searcher.build_ms + (time.perf_counter() - started) * 1000

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        candidates = self.hybrid_searcher.search(query, max(self.candidate_k, top_k))
        if not candidates:
            return []
        pairs = [
            [normalize_query(query), hit.document.text()]
            for hit in candidates
        ]
        scores = np.asarray(
            self.reranker.predict(pairs, batch_size=16, show_progress_bar=False),
            dtype=np.float32,
        ).reshape(-1)
        order = np.argsort(-scores, kind="stable")[:top_k]
        return [
            SearchHit(candidates[int(index)].document, float(scores[int(index)]))
            for index in order
        ]


def _hits(
    documents: Sequence[PolicyDocument],
    scores: Sequence[float],
    top_k: int,
    indices: Sequence[int] | None = None,
    require_positive: bool = False,
) -> list[SearchHit]:
    candidate_indices = list(range(len(documents))) if indices is None else list(indices)
    ordered = sorted(candidate_indices, key=lambda index: (-float(scores[index]), index))
    result = []
    for index in ordered:
        score = float(scores[index])
        if require_positive and score <= 0.0:
            continue
        result.append(SearchHit(documents[index], score))
        if len(result) >= top_k:
            break
    return result
