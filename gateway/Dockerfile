# syntax=docker/dockerfile:1
FROM node:22-slim AS build

WORKDIR /app

# Copy the gateway package and its local file: dependencies.
# The build context is the repo root (see docker-compose.yaml),
# so all COPY source paths are relative to the repo root.
COPY gateway/package.json gateway/package-lock.json ./
COPY interfaces/typescript ../interfaces/typescript
COPY sdk/typescript ../sdk/typescript

RUN npm ci

# Copy source and build.
COPY gateway/tsconfig.json ./
COPY gateway/src/ ./src/
RUN npm run build

# ─── Runtime ───────────────────────────────────────────────────
FROM node:22-slim AS runtime

WORKDIR /app

COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules/ ./node_modules/
COPY --from=build /app/dist/ ./dist/

ENV ENGINE_HOST=0.0.0.0
ENV ENGINE_PORT=8765

EXPOSE 8765

CMD ["node", "dist/main.js"]