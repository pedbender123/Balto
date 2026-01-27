#!/bin/bash

# Configurações
LOCAL_DIR="/home/pedro/balto_audio_data"
REMOTE_NAME="balto_drive" # O usuário precisa configurar este remote no rclone (rclone config)
REMOTE_DIR="BaltoAudioArchive"
LOG_FILE="/home/pedro/balto_audio_sync.log"

# Garantir que o log file existe
touch "$LOG_FILE"

echo "------------------------------------------------" >> $LOG_FILE
echo "$(date): Iniciando sincronização para o Drive..." >> $LOG_FILE

# Verifica se o diretório local existe
if [ ! -d "$LOCAL_DIR" ]; then
    echo "$(date): [ERRO] Diretório local $LOCAL_DIR não encontrado." >> $LOG_FILE
    exit 1
fi

# rclone move: Transfere arquivos e apaga do local após sucesso.
# --min-age 1h: Garante que não moveremos arquivos que o Balto ainda está escrevendo.
rclone move "$LOCAL_DIR" "$REMOTE_NAME:$REMOTE_DIR" \
    --min-age 1h \
    --drive-use-trash=false \
    --log-file="$LOG_FILE" \
    --log-level INFO \
    --delete-empty-src-dirs

if [ $? -eq 0 ]; then
    echo "$(date): [SUCESSO] Sincronização concluída e espaço liberado." >> $LOG_FILE
else
    echo "$(date): [ERRO] Falha na sincronização. Verifique o log." >> $LOG_FILE
fi
