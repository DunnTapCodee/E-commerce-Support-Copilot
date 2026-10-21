FROM python:3.11-slim

WORKDIR /app

COPY services/telemetry_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY contracts/ /app/contracts/
COPY services/telemetry_service/ /app/services/telemetry_service/

ENV PYTHONPATH=/app
ENV PORT=8003
ENV DB_PATH=/app/copilot_telemetry.sqlite3
ENV MOCK_ORDERS_PATH=/app/data/mock_orders.json

EXPOSE 8003

CMD ["uvicorn", "services.telemetry_service.src.main:app", "--host", "0.0.0.0", "--port", "8003"]
