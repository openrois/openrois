# syntax=docker/dockerfile:1
#
# The OpenRoIS Inspector. Build from the repository root:
#
#     docker build -f apps/inspector/Dockerfile -t openrois-inspector .
#     docker run --rm -p 127.0.0.1:8080:8080 openrois-inspector
#
# compose.yaml at the repository root runs it next to the gateway. The page connects to
# ws://localhost:8765 from the browser, or to the gateway its ?url= names.

FROM node:22-alpine AS build

WORKDIR /src
COPY interfaces/schema interfaces/schema
COPY interfaces/typescript interfaces/typescript
COPY sdk/javascript sdk/javascript
COPY apps/inspector apps/inspector
# The application links the types and the SDK of this tree, so both are built first.
RUN cd interfaces/typescript && npm ci && npm run build
RUN cd sdk/javascript && npm ci && npm install ../../interfaces/typescript --no-save \
    && npm run build
RUN cd apps/inspector && npm ci && npm run build


# Static files only: no Node.js at run time, and nginx runs as an unprivileged user.
FROM nginxinc/nginx-unprivileged:1.29-alpine

COPY apps/inspector/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/apps/inspector/dist /usr/share/nginx/html
EXPOSE 8080
