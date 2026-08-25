# syntax=docker/dockerfile:1
FROM node:22-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html ./
COPY vite.config.ts ./
COPY tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY src/ ./src/
COPY public/ ./public/
COPY eslint.config.js ./

RUN npm run build

# ─── Runtime ───────────────────────────────────────────────────
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]