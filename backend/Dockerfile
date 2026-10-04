FROM python:3.12-slim

# Headless Chromium is needed to read emails/faculty lists that pages fill in with JavaScript.
ARG INSTALL_PLAYWRIGHT=true
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt \
 && if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
      pip install playwright && playwright install --with-deps chromium && chmod -R a+rx /ms-playwright; \
    fi

COPY . .
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health')"

# Apply migrations, then serve. One worker: research jobs run on the in-process job pool.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
