#!/bin/sh
set -e

# serve.py reads PORT env; force it to 3001 so Next.js owns the Railway PORT
PORT=3001 python3 ./serve.py &
SERVE_PID=$!

# Next.js standalone reads PORT from env (set by Railway)
node server.js &
NEXT_PID=$!

trap "kill $SERVE_PID $NEXT_PID 2>/dev/null; exit" INT TERM
wait $NEXT_PID
