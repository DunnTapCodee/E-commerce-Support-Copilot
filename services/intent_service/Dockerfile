FROM python:3.11-slim

WORKDIR /app

COPY services/intent_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 --retries=5 -r /app/requirements.txt

COPY contracts/ /app/contracts/
COPY services/intent_service/ /app/services/intent_service/
COPY ML-model/ /app/ML-model/
COPY artifacts/ /app/artifacts/

ENV PYTHONPATH=/app
ENV PORT=8005
ENV INTENT_MODEL_DIR=/app/artifacts/models/intent
ENV INTENT_ROUTING_MODE=router

EXPOSE 8005

CMD ["python", "-m", "uvicorn", "services.intent_service.src.main:app", "--host", "0.0.0.0", "--port", "8005"]
