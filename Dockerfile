# 1. Imagem Base (Python leve)
FROM python:3.10-slim

# 2. Instala dependências do sistema para processamento de áudio
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 3. Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# 4. Copia APENAS o requirements.txt
COPY requirements_server.txt .

# 5. Instala as dependências
RUN pip install --no-cache-dir -r requirements_server.txt

# 6. Copia o resto do código-fonte
COPY . .

# 7. Expõe a porta que o websockets vai usar
EXPOSE 8765

# 8. Comando padrão para iniciar o servidor
CMD ["python", "-u", "server.py"]