FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app MPLBACKEND=Agg
WORKDIR /app

# PyBullet se compila desde el código fuente en Linux. Con setuptools recientes
# falla al empaquetar, por eso se fija setuptools y se desactiva el aislamiento.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && pip install --no-cache-dir "setuptools==65.5.1" wheel numpy pillow matplotlib \
 && pip install --no-cache-dir --no-build-isolation pybullet \
 && apt-get purge -y build-essential && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

COPY common ./common
COPY twin/twin.py .
EXPOSE 8080
CMD ["python", "twin.py"]
