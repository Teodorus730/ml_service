FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 GIT_PYTHON_REFRESH=quiet

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --no-dev --no-install-project --frozen

COPY src/ src/
RUN uv sync --no-dev --frozen

COPY artifact/ artifact/

COPY .dvc/config .dvc/config
COPY datasets/*.dvc datasets/
RUN uv run --no-sync dvc config --local core.no_scm true

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "kickstarter.service.app:app", "--host", "0.0.0.0", "--port", "8000"]