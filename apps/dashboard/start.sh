#!/bin/sh

# serve.py reads PORT env; force it to 3001 so Next.js owns the Railway PORT
PORT=3001 python3 ./serve.py &

# Next.js standalone — bind on all interfaces
HOSTNAME=0.0.0.0 node server.js
