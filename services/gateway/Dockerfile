FROM python:3.11-slim

WORKDIR /app

COPY services/gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY contracts/ /app/contracts/
COPY services/ /app/services/
COPY evaluation/ /app/evaluation/
COPY data/ /app/data/

ENV PYTHONPATH=/app
ENV PORT=8000
ENV INTENT_SERVICE_URL=http://intent_service:8005
ENV RAG_SERVICE_URL=http://rag_service:8002
ENV TELEMETRY_SERVICE_URL=http://telemetry_service:8003
ENV DOCUMENT_SERVICE_URL=http://document_service:8004
ENV CONVERSATION_SERVICE_URL=http://conversation_service:8006

EXPOSE 8000

CMD ["uvicorn", "services.gateway.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
