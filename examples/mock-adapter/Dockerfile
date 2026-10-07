# syntax=docker/dockerfile:1
#
# The mock adapter. Build from the repository root:
#
#     docker build -f examples/mock-adapter/Dockerfile -t openrois-mock-adapter .
#     docker run --rm --init -e OPENROIS_GATEWAY_URL=ws://<gateway-host>:8765 \
#         openrois-mock-adapter
#
# compose.yaml at the repository root runs it next to the gateway.

FROM python:3.12-slim AS build

WORKDIR /src
COPY interfaces/python interfaces/python
COPY components/core components/core
COPY engine engine
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    ./interfaces/python ./components/core ./engine


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# --pre: the OpenRoIS packages are alpha releases, the only versions in /wheels.
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links /wheels --pre \
    openrois-engine openrois-components-core

RUN useradd --system --uid 10001 --no-create-home openrois

WORKDIR /opt/mock-adapter
COPY examples/mock-adapter/mock_adapter.py examples/mock-adapter/openrois-profile.yaml ./
USER openrois

# OPENROIS_GATEWAY_URL overrides the gateway URL in openrois-profile.yaml.
CMD ["python", "mock_adapter.py", "--config", "openrois-profile.yaml"]
