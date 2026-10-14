FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY common ./common
COPY ap/ap_relay.py .
CMD ["python", "ap_relay.py"]
