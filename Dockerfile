FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data
ENV DATABASE_URL=sqlite:////app/data/contentforge.db

CMD sh -c "python -m uvicorn app:app --host 0.0.0.0 --port \${PORT:-8080}"