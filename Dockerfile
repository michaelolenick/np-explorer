FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
ENV NP_DATA_DIR=/data NP_LOG_DIR=/data/log LC_ALL=C.UTF-8
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade 0002 && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
