FROM python:3.11.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    python3-dev \
    libffi-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN set -eux; \
    pip install -r requirements.txt; \
    pip install --no-cache-dir --upgrade "git+https://github.com/natalieee-n/bondage-club-bot-core.git@v0.1.2"

COPY . /app

CMD ["python", "server.py"]
