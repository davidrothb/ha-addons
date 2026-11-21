#!/bin/sh
# Lokální běh mimo Home Assistant (macOS: caffeinate brání uspání).
cd "$(dirname "$0")" && exec caffeinate -i python3 poll.py "$@"
