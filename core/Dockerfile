# The OpenRoIS gateway. Build from the repository root:
#   docker build -f core/Dockerfile -t openrois/gateway .
FROM python:3.12-slim

WORKDIR /opt/openrois

# The core package depends on the interface types, which are not published
# yet, so both are installed from the source tree.
COPY interfaces/python ./interfaces/python
COPY core ./core
RUN pip install --no-cache-dir ./interfaces/python ./core

ENV OPENROIS_HOST=0.0.0.0
ENV OPENROIS_PORT=8765

EXPOSE 8765

CMD openrois-gateway --host "$OPENROIS_HOST" --port "$OPENROIS_PORT"
