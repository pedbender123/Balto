# 1. Imagem Base (Python leve)
FROM python:3.10-slim

# 2. Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# 3. Copia APENAS o requirements.txt
COPY requirements_server.txt .

# 4. Instala as dependências
RUN pip install --no-cache-dir -r requirements_server.txt

# 5. Copia o resto do código-fonte
COPY . .

# 6. Expõe a porta que o websockets vai usar
EXPOSE 8765

# 7. Comando padrão para iniciar o servidor (COM A CORREÇÃO '-u')
CMD ["python", "-u", "server.py"]