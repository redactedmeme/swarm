FROM oven/bun:1.1-slim

WORKDIR /app

COPY package.json ./
RUN bun install

COPY . .

ENV NODE_ENV=production
ENV BRIDGE_PORT=8080

EXPOSE 8080

CMD ["bun", "run", "index.ts"]
