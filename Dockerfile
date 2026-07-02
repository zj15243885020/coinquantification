FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

RUN mkdir -p /app/vault /app/logs /app/data_cache

ENV PYTHONUNBUFFERED=1
ENV CQUANT_LOG_FORMAT=console

CMD ["python", "main.py", "backtest", "--strategy", "dual_ma", "--symbol", "BTC/USDT"]
