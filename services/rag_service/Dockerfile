FROM python:3.11-slim

WORKDIR /app

COPY services/rag_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY contracts/ /app/contracts/
COPY services/rag_service/ /app/services/rag_service/

ENV PYTHONPATH=/app
ENV PORT=8002
ENV POLICIES_PATH=/app/data/knowledge_base/policies.json
ENV INDEX_PATH=/app/artifacts/vector_store/policy_index.pkl

EXPOSE 8002

CMD ["uvicorn", "services.rag_service.src.main:app", "--host", "0.0.0.0", "--port", "8002"]
