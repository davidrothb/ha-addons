# Debian-based image: matplotlib ships ready-made wheels for it on amd64 and aarch64.
FROM python:3.13-slim

# tzdata provides Asia/Taipei for zoneinfo
RUN pip install --no-cache-dir matplotlib==3.11.* tzdata

ENV PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib
COPY poll.py history.py ha.py plot.py /app/

CMD ["sh", "-c", "mkdir -p /share/wsjjsc_tracker && exec python3 /app/poll.py --csv /share/wsjjsc_tracker/gym_occupancy.csv --plot-out /homeassistant/www/wsjjsc_tracker/gym_occupancy.png"]
