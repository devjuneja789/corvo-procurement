FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
COPY scripts ./scripts
COPY demo ./demo
RUN mkdir -p /var/data
ENV PYTHONUNBUFFERED=1 PORT=8000 DATABASE_PATH=/var/data/app.sqlite3
EXPOSE 8000
CMD ["python", "-m", "app.server"]
