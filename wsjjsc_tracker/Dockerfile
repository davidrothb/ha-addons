FROM python:3.13-alpine

# zoneinfo needs the tz database for Asia/Taipei
RUN apk add --no-cache tzdata

ENV PYTHONUNBUFFERED=1
COPY poll.py /app/poll.py

CMD ["sh", "-c", "mkdir -p /share/wsjjsc_tracker && exec python3 /app/poll.py --csv /share/wsjjsc_tracker/gym_occupancy.csv"]
