FROM python:3.13-slim

# tzdata: zoneinfo needs it for the time zone the Supervisor passes in TZ
RUN pip install --no-cache-dir websocket-client==1.8.0 tzdata

ENV PYTHONUNBUFFERED=1
COPY app.py iding.py menu.py index.html /app/

CMD ["python3", "/app/app.py"]
