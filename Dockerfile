FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./

RUN uv sync --no-dev --no-install-project

COPY . .

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "app/main.py", "--server.port=8501",  "--server.address=0.0.0.0"]
