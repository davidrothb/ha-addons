FROM python:3.13-slim

RUN pip install --no-cache-dir websocket-client==1.8.0

ENV PYTHONUNBUFFERED=1
COPY app.py index.html /app/

CMD ["python3", "/app/app.py"]
