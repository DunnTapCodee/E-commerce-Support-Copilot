FROM python:3.11-slim

WORKDIR /app

COPY services/document_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY contracts/ /app/contracts/
COPY services/document_service/ /app/services/document_service/
COPY data/ /app/data/

ENV PYTHONPATH=/app
ENV PORT=8004

EXPOSE 8004

CMD ["python", "-m", "uvicorn", "services.document_service.src.main:app", "--host", "0.0.0.0", "--port", "8004"]
