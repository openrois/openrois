# The OpenRoIS gateway. Build from the repository root:
#   docker build -f core/Dockerfile -t openrois/gateway .
FROM python:3.12-slim

WORKDIR /opt/openrois

# The core package depends on the interface types, which are not published
# yet, so both are installed from the source tree.
COPY interfaces/python ./interfaces/python
COPY core ./core
RUN pip install --no-cache-dir ./interfaces/python ./core

# Every option can come from OPENROIS_* variables or from a YAML file mounted at
# /etc/openrois/gateway.yaml (see openrois_core.gateway). Command line beats both.
ENV OPENROIS_HOST=0.0.0.0
ENV OPENROIS_PORT=8765
ENV OPENROIS_GATEWAY_CONFIG=/etc/openrois/gateway.yaml
RUN mkdir -p /etc/openrois && printf '{}\n' > /etc/openrois/gateway.yaml

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=3s CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=2)"

CMD ["openrois-gateway"]
