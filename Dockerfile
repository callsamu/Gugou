ARG PYTHON_VERSION=3.12
FROM ghcr.io/astral-sh/uv:alpine

ARG SERVICE
ARG PYTHON_VERSION
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=automatic

# The Alpine uv image ships uv but no Python interpreter, so let uv install
# the requested standalone CPython build.
RUN uv python install "${PYTHON_VERSION}"

# Workspace manifests first so dependency layers stay cached.
COPY pyproject.toml uv.lock ./
COPY packages/common/pyproject.toml packages/common/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/downloader/pyproject.toml services/downloader/pyproject.toml
COPY services/extractor/pyproject.toml services/extractor/pyproject.toml
COPY services/frontier/pyproject.toml services/frontier/pyproject.toml
COPY services/searcher/pyproject.toml services/searcher/pyproject.toml

# Dependencies first (project sources are not needed yet) so this layer stays cached.
RUN uv sync --frozen --no-dev --no-install-project --package "${SERVICE}"

COPY packages/common packages/common
COPY services services

# Install the workspace projects now that their sources are present.
RUN uv sync --frozen --no-dev --package "${SERVICE}"

ENV PATH="/app/.venv/bin:$PATH"
CMD ["sh", "-c", "echo 'override with a service command'"]
