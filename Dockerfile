FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    WEB_CONCURRENCY=1 \
    GUNICORN_TIMEOUT=120

WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY . .
USER app
EXPOSE 8080
CMD ["/bin/sh", "-c", "exec gunicorn main:app --bind 0.0.0.0:${PORT} --worker-class uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY} --timeout ${GUNICORN_TIMEOUT} --graceful-timeout 30 --keep-alive 5 --access-logfile - --error-logfile -"]
