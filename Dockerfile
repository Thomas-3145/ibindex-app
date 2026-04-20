FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY shared/ shared/
COPY app/ app/
COPY scraper/ scraper/

RUN uv sync --no-dev

EXPOSE 8501

CMD [".venv/bin/streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
