#!/bin/sh
set -e

# serve.py is one level up (repo root layout on Railway)
python3 ../serve.py &
SERVE_PID=$!

node server.js &
NEXT_PID=$!

trap "kill $SERVE_PID $NEXT_PID 2>/dev/null; exit" INT TERM
wait $NEXT_PID
