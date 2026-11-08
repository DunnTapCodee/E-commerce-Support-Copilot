FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY services/document_service/requirements.txt ./service-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r service-requirements.txt

COPY contracts/ contracts/
COPY services/document_service/ services/document_service/
COPY data/ data/

ENV PYTHONPATH=/app
ENV PORT=8004

EXPOSE 8004

CMD ["python", "-m", "uvicorn", "services.document_service.src.main:app", "--host", "0.0.0.0", "--port", "8004"]

