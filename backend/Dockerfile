FROM python:3.10-slim

# Instalação de dependências do sistema
# libsndfile1: necessário para processamento de áudio (soundfile/librosa)
# ffmpeg: necessário para decodificação de áudio (pydub/subprocess)
# gcc, g++: necessários para compilar bibliotecas numéricas ou de áudio
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    gcc \
    g++ \
    make \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /backend

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código fonte
COPY . .

# Cria usuário não-root por segurança
RUN useradd -m -u 1000 balto_user && \
    chown -R balto_user:balto_user /backend

# Define o PYTHONPATH para garantir que imports 'from app...' funcionem
ENV PYTHONPATH=/backend

# Troca para o usuário não-root
USER balto_user

# Executa o servidor em modo unbuffered (logs aparecem instantaneamente)
CMD ["python", "-u", "-m", "app.main"]
