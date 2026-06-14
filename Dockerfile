FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data
ENV DATABASE_URL=sqlite:////app/data/contentforge.db

EXPOSE 8080

CMD python -c "import os; import uvicorn; from app import app; uvicorn.run(app, host='0.0.0.0', port=int(os.getenv('PORT', '8080')))"
