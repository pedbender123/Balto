FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    gcc \
    g++ \
    make \
    gosu \
    swig \
    rclone \
    libwebrtc-audio-processing-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /backend

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

COPY . .

# Cria usuário não-root
RUN useradd -m -u 1000 balto_user && \
    chown -R balto_user:balto_user /backend

ENV PYTHONPATH=/backend

# EntryPoint fora de /backend pra não ser sobrescrito pelo bind mount ./backend:/backend
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# mantém o que funcionava antes
CMD ["python", "-u", "-m", "app.main"]
