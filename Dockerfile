FROM python:3.11-slim

WORKDIR /app

RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY config ./config
COPY fixtures ./fixtures

RUN pip install --no-cache-dir . \
    && chown -R appuser:appuser /app

USER appuser

ENV EVENTS_OFFLINE=1 \
    LIVE_LLM=0 \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "events_briefing", "demo", "--offline"]
