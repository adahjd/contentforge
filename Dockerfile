FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data
ENV DATABASE_URL=sqlite:////app/data/contentforge.db

RUN chmod +x start.sh

CMD ["./start.sh"]