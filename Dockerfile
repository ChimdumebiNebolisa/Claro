# Claros backend — Cloud Run
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements-server.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY main.py parser.py agent.py exporter.py ./
COPY frontend ./frontend

# Cloud Run listens on PORT (default 8080)
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
