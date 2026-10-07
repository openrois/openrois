# syntax=docker/dockerfile:1
#
# The mock adapter. Build from the repository root:
#
#     docker build -f examples/mock-adapter/Dockerfile -t openrois-mock-adapter .
#     docker run --rm --init -e OPENROIS_GATEWAY_URL=ws://<gateway-host>:8765 \
#         openrois-mock-adapter
#
# compose.yaml at the repository root runs it next to the gateway. Settings come from
# OPENROIS_GATEWAY_URL, OPENROIS_MOCK_ENGINE_ID and OPENROIS_MOCK_TIME_SCALE, or from
# flags after the image name. See examples/mock-adapter/README.md.

FROM python:3.12-slim AS build

WORKDIR /src
COPY interfaces/python interfaces/python
COPY engine engine
COPY components/core components/core
COPY components/common components/common
# Build wheels for the four packages and every dependency, so the runtime stage
# installs offline and carries no source tree or build tools.
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    ./interfaces/python ./engine ./components/core ./components/common


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# --pre: the OpenRoIS packages are alpha releases, the only versions in /wheels.
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links /wheels --pre \
    openrois-engine openrois-components-core openrois-components-common

RUN useradd --system --uid 10001 --no-create-home openrois

WORKDIR /opt/mock-adapter
COPY examples/mock-adapter/mock_adapter.py ./
USER openrois

ENTRYPOINT ["python", "mock_adapter.py"]
