# PMRS API image (Step 31). Local use only; no cloud deployment is approved.
#
# Nothing secret and no data is baked in: the MovieLens CSVs and the frozen serving
# artifact are mounted read-only at run time (see compose.app.yaml), and settings come
# from environment variables. The artifact is a pickle, so it must be one this project
# built; its SHA-256 manifest is verified when the API starts.
#
# Base image tags are not yet pinned by digest; record the digest after the first pull.

FROM python:3.12-slim AS builder
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv==0.13.6
WORKDIR /app
COPY pyproject.toml uv.lock ./
# UV_SYNC_ARGS: "--no-dev" keeps the image small, BUT pmrs.api.app imports
# pmrs.evaluation.final, which imports plotly, and plotly is currently declared only in
# the dev group. Until that is settled (open owner decision), build with
# UV_SYNC_ARGS="" to include the dev group. See README "Docker".
ARG UV_SYNC_ARGS="--no-dev"
RUN uv sync --locked --no-install-project ${UV_SYNC_ARGS}

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src
RUN useradd --system --uid 10001 --no-create-home pmrs
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
USER 10001
EXPOSE 8000
CMD ["uvicorn", "pmrs.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
