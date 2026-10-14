FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY common ./common
COPY node/node_esp32.py .
CMD ["python", "node_esp32.py"]
