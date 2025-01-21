FROM python:3.10.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "uvicorn[standard]" "httpx[http2]" && \
    rm -rf /root/.cache/pip/* && \
    rm -rf /root/.cache && \
    find /usr/local -type d -name "__pycache__" -exec rm -rf {} + && \
    find /usr/local -type f -name "*.py[co]" -delete && \
    find /usr/local -type d -name "*.dist-info" -exec rm -rf {} + && \
    find /usr/local -type d -name "*.egg-info" -exec rm -rf {} +

COPY app app/

ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["/usr/local/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
