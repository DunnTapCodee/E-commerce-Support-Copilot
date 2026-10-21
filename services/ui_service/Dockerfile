FROM python:3.11-slim

WORKDIR /app

COPY services/ui_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/ui_service/ /app/services/ui_service/

ENV PYTHONPATH=/app
ENV PORT=8501
ENV GATEWAY_URL=http://gateway:8000

EXPOSE 8501

CMD ["streamlit", "run", "services/ui_service/src/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
