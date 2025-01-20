FROM python:3.10.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:$PATH" \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir uvicorn && \
    rm -rf /root/.cache/pip/* && \
    rm -rf /root/.cache && \
    find /usr/local -type d -name "__pycache__" -exec rm -rf {} + && \
    find /usr/local -type f -name "*.py[co]" -delete && \
    find /usr/local -type d -name "*.dist-info" -exec rm -rf {} + && \
    find /usr/local -type d -name "*.egg-info" -exec rm -rf {} +

COPY app app/

EXPOSE 8000

CMD ["/usr/local/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
