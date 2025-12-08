FROM python:3.10-slim

# Instala libs de sistema (sndfile é vital para audio)
# Instala libs de sistema (sndfile + ffmpeg + gcc)
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    gcc \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /backend

# Copia requirements e instala
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código da pasta backend
COPY . .

# Expõe porta
EXPOSE 8765

# Ajuste no PYTHONPATH para ele achar o módulo 'app' e rodar o server
ENV PYTHONPATH=/backend
CMD ["python", "-u", "app/server.py"]