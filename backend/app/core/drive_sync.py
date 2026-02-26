import asyncio
import os
import shutil
import subprocess
import logging
from datetime import datetime
from app import db
from app.core import config

logger = logging.getLogger(__name__)

async def drive_sync_loop():
    """
    Loop que roda em background para exportar o banco e sincronizar áudios com o Google Drive.
    """
    if not os.environ.get("DRIVE_SYNC_ENABLED", "true").lower() in ("true", "1", "yes"):
        logger.info("DRIVE_SYNC: Sincronização desativada.")
        return

    interval_min = int(os.environ.get("DRIVE_SYNC_INTERVAL_MINUTES", "30"))
    remote_name = os.environ.get("DRIVE_SYNC_REMOTE_NAME", "balto_drive")
    remote_dir = os.environ.get("DRIVE_SYNC_REMOTE_DIR", "BaltoAudioArchive")
    local_dir = os.environ.get("AUDIO_DUMP_DIR", "/backend/app/audio_dumps")
    rclone_config = os.environ.get("RCLONE_CONFIG_PATH", "/backend/rclone.conf")

    logger.info(f"DRIVE_SYNC: Iniciado. Intervalo: {interval_min}min. Remote: {remote_name}:{remote_dir}")

    while True:
        try:
            # Aguarda o intervalo
            await asyncio.sleep(interval_min * 60)
            
            logger.info("DRIVE_SYNC: Iniciando ciclo de sincronização...")

            # 1. Exportar CSV atualizado
            csv_path = os.path.join(local_dir, "interacoes_export.csv")
            success = await asyncio.to_thread(db.exportar_interacoes_csv, csv_path)
            
            if not success:
                logger.error("DRIVE_SYNC: Falha ao exportar CSV. Abortando ciclo.")
                continue

            # 2. Executar rclone copy para o CSV (vai na hora, sem min-age)
            cmd_csv = [
                "rclone", "copy", csv_path, f"{remote_name}:{remote_dir}",
                "--config", rclone_config,
                "--log-level", "INFO"
            ]
            
            logger.info(f"DRIVE_SYNC: Copiando CSV para o Drive...")
            try:
                process_csv = await asyncio.create_subprocess_exec(
                    *cmd_csv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await process_csv.communicate()
            except Exception as e:
                logger.error(f"DRIVE_SYNC: Erro ao copiar CSV: {e}")

            # 3. Executar rclone move para os áudios
            # --min-age 5m: evita mover arquivos de áudio sendo gravados agora
            archiver_dir = os.path.join(local_dir, "archiver")
            cmd_audio = [
                "rclone", "move", archiver_dir, f"{remote_name}:{remote_dir}/archiver",
                "--config", rclone_config,
                "--min-age", "5m",
                "--drive-use-trash=false",
                "--delete-empty-src-dirs",
                "--log-level", "INFO"
            ]
            
            logger.info(f"DRIVE_SYNC: Movendo áudios arquivados...")
            
            process = await asyncio.create_subprocess_exec(
                *cmd_audio,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("DRIVE_SYNC: Sincronização concluída com sucesso. Espaço local liberado.")
            else:
                logger.error(f"DRIVE_SYNC: Erro no rclone (code {process.returncode}).")
                if stderr:
                    logger.error(f"DRIVE_SYNC stderr: {stderr.decode()}")
                    
        except asyncio.CancelledError:
            logger.info("DRIVE_SYNC: Task cancelada.")
            break
        except Exception as e:
            logger.error(f"DRIVE_SYNC: Erro inesperado: {e}")
            await asyncio.sleep(60) # Espera um pouco antes de tentar de novo caso dê crash
