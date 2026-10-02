FROM python:3.13-slim

WORKDIR /app

# Dependencies first, for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/

# data/ (player memory, audit log) is a volume; create it so a fresh named
# volume inherits the ownership.
RUN useradd --system --uid 1000 --home-dir /app godbot \
 && mkdir -p /app/data && chown godbot:godbot /app/data

ENV PYTHONUNBUFFERED=1
USER godbot

CMD ["python", "-m", "bot.main"]
