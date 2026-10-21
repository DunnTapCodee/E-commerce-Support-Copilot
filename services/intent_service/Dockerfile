FROM python:3.11-slim

WORKDIR /app

COPY services/intent_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY contracts/ /app/contracts/
COPY services/intent_service/ /app/services/intent_service/

ENV PYTHONPATH=/app
ENV PORT=8001
ENV MODEL_PATH=/app/artifacts/models/intent_model.pkl

EXPOSE 8001

CMD ["uvicorn", "services.intent_service.src.main:app", "--host", "0.0.0.0", "--port", "8001"]
