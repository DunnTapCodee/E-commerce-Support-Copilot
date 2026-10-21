FROM python:3.11-slim

WORKDIR /app

COPY services/gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY contracts/ /app/contracts/
COPY services/gateway/ /app/services/gateway/

ENV PYTHONPATH=/app
ENV PORT=8000
ENV INTENT_SERVICE_URL=http://intent_service:8001
ENV RAG_SERVICE_URL=http://rag_service:8002
ENV TELEMETRY_SERVICE_URL=http://telemetry_service:8003

EXPOSE 8000

CMD ["uvicorn", "services.gateway.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
