FROM oven/bun:1.1-slim AS builder

WORKDIR /app
COPY package.json bun.lockb* ./
RUN bun install --frozen-lockfile 2>/dev/null || bun install

COPY . .
RUN bun run build 2>/dev/null || echo "tsc unavailable — running from source"

FROM oven/bun:1.1-slim
WORKDIR /app

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist 2>/dev/null || true
COPY --from=builder /app/src ./src
COPY --from=builder /app/*.ts ./
COPY --from=builder /app/*.json ./

ENV NODE_ENV=production
ENV BRIDGE_PORT=8080

EXPOSE 8080 4001

# Run from source with Bun (avoids tsc dependency in prod)
CMD ["bun", "run", "index.ts"]
