# E-commerce Support Copilot

Five-service agent workbench: Streamlit UI, FastAPI gateway, bilingual intent
classification, policy retrieval/drafting, and SQLite audit telemetry.

Module 1 NLU implementation and commands: [README_MODULE1.md](services/intent_service/README_MODULE1.md). The one-run Kaggle notebook is `kaggle/kernels/k00-end-to-end-nlu/k00_end_to_end_nlu.ipynb`.
New NLU artifacts must be trained and deployed before the intent API becomes healthy.
The source-only Module 1 update includes no measured model results.

To install service dependencies and launch locally, run `./run.sh`. The script creates `.venv` if needed. Module 1 training is separate; until its artifacts are installed, the intent service reports `degraded`. See [its runbook](services/intent_service/README_MODULE1.md).
For Docker, populate `artifacts/models/intent/`, configure `.env` from
`.env.example`, and follow the calibrated deployment commands in the Module 1 guide.

The SQLite database `copilot_telemetry.sqlite3` is created beside the source on first run. Keep it local; it contains customer query text for this demo.
The UI produces drafts for human review. Approve/Edit actions record an audit entry; they do not send a customer message or execute financial transactions. Orders and policy data in this repository are demonstration data.

## Module 2: Retrieval experiments

The retrieval benchmark compares the existing TF-IDF + cosine baseline, BM25, dense embeddings, BM25+dense RRF, and RRF with cross-encoder reranking. It uses `data/retrieval_eval.json`, a manually labeled Vietnamese query set covering every active policy. All methods search the same 47 active policies and use `title + content`; inactive policies are filtered before ranking. Tags are excluded by default and can be tested as an ablation.

Install the optional experiment dependencies and run the benchmark from the repository root:

```powershell
python -m pip install -r requirements-retrieval-experiments.txt
python scripts/benchmark_retrieval.py
```

The first dense run downloads the model. Defaults use `keepitreal/vietnamese-sbert` and `BAAI/bge-reranker-base`; pass `--dense-model BAAI/bge-m3` to compare BGE-M3. Dense query latency includes query embedding; reranked latency also includes candidate scoring. The report records index/model setup separately and writes results to `reports/module2_retrieval_benchmark.json`. The target is p95 query latency below 15 ms. FAISS `IndexFlatIP` is used when its Python wheel is available; otherwise the exact NumPy cosine implementation is used, which is sufficient for this 47-document corpus.

Use `--methods tfidf,bm25` for a quick sparse-only run, or add `--include-tags` to repeat all selected methods with policy tags included.

### Selecting retrieval in the RAG service

The RAG API now uses BM25 by default. Choose a runtime method with `RETRIEVAL_METHOD=tfidf|bm25|dense|hybrid|reranked`; `/health` reports the active method. TF-IDF remains the lightweight legacy option. The `dense` method uses the embedding model, `hybrid` fuses BM25 and dense rankings with RRF, and `reranked` adds the cross-encoder over the hybrid candidates. Model IDs and the CPU/GPU device can be set with `DENSE_EMBEDDING_MODEL`, `RERANKER_MODEL`, and `RETRIEVAL_DEVICE`.

BM25 is installed with the RAG service. Dense, hybrid, and reranked modes need the optional model packages. For Docker, set `INSTALL_RAG_MODEL_DEPS=true` when building, then choose `RETRIEVAL_METHOD` in the environment and rebuild the RAG image. The first start downloads model weights into the persistent `rag_model_cache` volume. For local Python runs, install `requirements-retrieval-experiments.txt` first. A model package or model-loading error fails service startup with a clear error instead of silently changing retrieval methods.

The current CPU benchmark has BM25 p95 latency below 1 ms, while dense and reranked modes exceed the product target of 15 ms. This is why BM25 is the runtime default; the model-based modes are available for experiments or deployment on a measured accelerator. The existing gateway intent and policy guardrails remain in place, including escalation when the intent is out of scope or no usable policy citations are returned. Retrieval scores are method-specific and must not be compared as if they shared one scale.
