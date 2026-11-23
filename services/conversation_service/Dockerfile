FROM python:3.11-slim

WORKDIR /app

COPY services/conversation_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY contracts /app/contracts
COPY services/conversation_service /app/services/conversation_service
COPY scripts /app/scripts
COPY data /app/data

ENV PYTHONPATH=/app
ENV PORT=8006

EXPOSE 8006

CMD ["python", "-m", "uvicorn", "services.conversation_service.src.main:app", "--host", "0.0.0.0", "--port", "8006"]
