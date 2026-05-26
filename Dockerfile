FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
ENV FLASK_ENV=production

EXPOSE 8080

CMD gunicorn app:app --workers 4 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT
