#!/bin/sh
# Lokální běh mimo Home Assistant: http://localhost:8099/?as=Jana
# Pro test z telefonu na stejné wifi: ./run.sh --host 0.0.0.0
cd "$(dirname "$0")" && exec python3 app.py --dev "$@"
