ARG PYTHON_VERSION=3.14t

FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder
ARG PYTHON_VERSION
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
ENV UV_PYTHON=$PYTHON_VERSION

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

RUN uv python install "$PYTHON_VERSION" --compile-bytecode

WORKDIR /build
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --python "$PYTHON_VERSION" --frozen --no-install-project --no-dev
ADD . /build
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --python "$PYTHON_VERSION" --frozen --no-dev


FROM debian:bookworm-slim

COPY --from=builder /opt/uv-python /opt/uv-python
COPY --from=builder /build /code
WORKDIR /code

ENV PATH="/code/.venv/bin:$PATH"
ENV DISABLE_SQLALCHEMY_CEXT_RUNTIME=1
ENV MSGPACK_PUREPYTHON=1

# Install curl for health checks and CA certificates for outbound HTTPS
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -c "import sys, sysconfig; sys.exit(0 if sysconfig.get_config_var('Py_GIL_DISABLED') == 1 else 'Python is not a free-threaded build')"

COPY cli_wrapper.sh /usr/bin/pasarguard-cli
RUN chmod +x /usr/bin/pasarguard-cli

COPY tui_wrapper.sh /usr/bin/pasarguard-tui
RUN chmod +x /usr/bin/pasarguard-tui

# Copy healthcheck script
COPY healthcheck.sh /code/healthcheck.sh
RUN chmod +x /code/healthcheck.sh

RUN chmod +x /code/start.sh

ENTRYPOINT ["/code/start.sh"]
