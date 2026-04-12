FROM python:3.12-slim

WORKDIR /app

# Install system deps for soundfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
COPY ui/ ui/
COPY data/ data/
COPY pipeline/ pipeline/

# Install dependencies including STT for browser mic support
RUN uv sync --no-dev --frozen --extra stt

# Seed the question database from YAML content files
RUN uv run python pipeline/seed_db.py

# Cloud mode by default
ENV OLMEC_MODE=cloud
ENV OLMEC_HOST=0.0.0.0
ENV OLMEC_PORT=8000

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "olmec.main:app", "--host", "0.0.0.0", "--port", "8000"]
