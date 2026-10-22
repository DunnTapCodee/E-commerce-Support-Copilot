FROM python:3.11-slim

WORKDIR /app

COPY services/rag_service/requirements.txt /app/requirements.txt
COPY requirements-retrieval-experiments.txt /app/requirements-retrieval-experiments.txt
ARG INSTALL_RAG_MODEL_DEPS=false
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN if [ "$INSTALL_RAG_MODEL_DEPS" = "true" ]; then pip install --no-cache-dir -r /app/requirements-retrieval-experiments.txt; fi

COPY contracts/ /app/contracts/
COPY services/rag_service/ /app/services/rag_service/

ENV PYTHONPATH=/app
ENV PORT=8002
ENV POLICIES_PATH=/app/data/knowledge_base/policies.json
ENV INDEX_PATH=/app/artifacts/vector_store/policy_index.pkl
ENV RETRIEVAL_METHOD=bm25
ENV DENSE_EMBEDDING_MODEL=keepitreal/vietnamese-sbert
ENV RERANKER_MODEL=BAAI/bge-reranker-base
ENV RETRIEVAL_DEVICE=cpu
ENV HF_HOME=/models/huggingface

EXPOSE 8002

CMD ["uvicorn", "services.rag_service.src.main:app", "--host", "0.0.0.0", "--port", "8002"]
