#!/usr/bin/env bash
set -euo pipefail

APP_AUDIO_ROOT="${APP_AUDIO_ROOT:-/backend/app/audio_dumps}"
CADASTRO_DIR="${CADASTRO_DIR:-${APP_AUDIO_ROOT}/cadastros_voz}"

# Se você já tinha um named volume antigo, montaremos ele aqui no compose:
LEGACY_ROOT="${LEGACY_ROOT:-/backend/_audio_volume_legacy}"

APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"

echo "[ENTRYPOINT] APP_AUDIO_ROOT=$APP_AUDIO_ROOT"
echo "[ENTRYPOINT] CADASTRO_DIR=$CADASTRO_DIR"
echo "[ENTRYPOINT] LEGACY_ROOT=$LEGACY_ROOT"
echo "[ENTRYPOINT] APP_UID=$APP_UID APP_GID=$APP_GID"

# 1) Garante diretórios
mkdir -p "$CADASTRO_DIR"

# 2) Migração automática do volume antigo -> pasta do host (só se necessário)
# Regra: se legacy tem arquivos e a pasta do app está "vazia", copia tudo.
if [ -d "$LEGACY_ROOT" ] && [ "$(ls -A "$LEGACY_ROOT" 2>/dev/null || true)" ]; then
  if [ ! "$(ls -A "$APP_AUDIO_ROOT" 2>/dev/null || true)" ]; then
    echo "[ENTRYPOINT] Migrando áudio do legacy volume para o bind mount do host..."
    cp -a "$LEGACY_ROOT/." "$APP_AUDIO_ROOT/" || true
    echo "[ENTRYPOINT] Migração concluída."
  else
    echo "[ENTRYPOINT] Migração não necessária (pasta do app já tem arquivos)."
  fi
else
  echo "[ENTRYPOINT] Legacy vazio ou não montado."
fi

# 3) Corrige permissões do diretório montado (precisa ser root)
#    Isso resolve o Permission denied do WAV SEM exigir comando no host.
chown -R "${APP_UID}:${APP_GID}" "$APP_AUDIO_ROOT" || true
chmod -R ug+rwX "$APP_AUDIO_ROOT" || true

# 4) Drop privileges e roda o CMD
exec gosu "${APP_UID}:${APP_GID}" "$@"
