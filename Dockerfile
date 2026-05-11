# MediPath — Python + Flask; copy the whole repo so static HTML/CSS/JS and SQLite paths match local dev.
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEDIPATH_HOST=0.0.0.0 \
    MEDIPATH_PORT=5005

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5005

CMD ["python", "backend/app.py"]
