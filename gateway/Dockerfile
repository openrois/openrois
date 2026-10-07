# syntax=docker/dockerfile:1
#
# The OpenRoIS gateway. Build from the repository root:
#
#     docker build -f gateway/Dockerfile -t openrois-gateway .
#     docker run --rm -p 127.0.0.1:8765:8765 openrois-gateway
#
# Settings come from OPENROIS_GATEWAY_* environment variables or flags after the image
# name. See gateway/README.md.

FROM python:3.12-slim AS build

WORKDIR /src
COPY interfaces/python interfaces/python
COPY engine engine
COPY gateway gateway
# Build wheels for the three packages and every dependency, so the runtime stage
# installs offline and carries no source tree or build tools.
RUN pip wheel --no-cache-dir --wheel-dir /wheels ./interfaces/python ./engine ./gateway


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# --pre: the OpenRoIS packages are alpha releases, the only versions in /wheels.
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links /wheels --pre openrois-gateway

RUN useradd --system --uid 10001 --no-create-home openrois
USER openrois

# Inside the container the gateway listens on every interface, so Docker can publish
# the port. Publish it on 127.0.0.1 unless the network is trusted: the gateway does not
# authenticate its peers.
ENV OPENROIS_GATEWAY_HOST=0.0.0.0
EXPOSE 8765

# The gateway handles SIGTERM itself and exits with code 0 after closing connections.
ENTRYPOINT ["openrois-gateway"]
