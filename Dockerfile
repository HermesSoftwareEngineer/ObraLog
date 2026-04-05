FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY . /app

ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["sh", "-c", "gunicorn backend.main:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --timeout 120"]
