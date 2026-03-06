FROM ghcr.io/astral-sh/uv:trixie-slim AS builder
ENV UV_COMPILE_BYTECODE=1 
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV UV_PYTHON_INSTALL_DIR=/python
ENV UV_PYTHON_PREFERENCE=only-managed
ENV UV_PROJECT_ENVIRONMENT=/.venv

RUN uv python install 3.13

WORKDIR /app
# Instala dependencias sin proyecto, queda como capa para cachear
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

COPY . /app
# Instala el proyecto, esto se cachea por separado de las dependencias
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Imagen final sin UV
FROM debian:trixie-slim

ARG UID=1000
ARG GID=1000
RUN groupadd --system --gid ${GID} nonroot \
 && useradd --system --gid ${GID} --uid ${UID} --create-home nonroot

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar todo desde el builder
COPY --from=builder --chown=nonroot:nonroot /python /python
COPY --from=builder --chown=nonroot:nonroot /.venv /.venv
COPY --from=builder --chown=nonroot:nonroot /app /app


ENV PATH="/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /app/staticfiles /app/archivos_pdf /app/archivos_img /app/.logs \
    && chown -R nonroot:nonroot /app

USER nonroot
WORKDIR /app
