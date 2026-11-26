FROM python:3.12-slim AS app

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 ticketdesk \
    && useradd --uid 10001 --gid 10001 --no-create-home ticketdesk \
    && install -d -o 10001 -g 10001 /app/uploads

COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=3).close()"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM app AS test
COPY requirements-test.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements-test.txt
COPY --chown=10001:10001 tests/ ./tests/
USER 10001:10001

FROM app AS runtime
ENV APP_ENV=production DEBUG=false
USER 10001:10001
