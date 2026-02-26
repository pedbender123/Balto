import os
import time
import wave
import asyncio
import logging
from datetime import datetime
from collections import defaultdict
from app.core import config
from pathlib import Path

logger = logging.getLogger(__name__)

class AudioArchiver:
    """
    Grava áudio de forma assíncrona em background.
    Organiza por data e balcão, separando RAW de PROCESSED.
    Agrupa em arquivos de 60 segundos.
    """
    def __init__(self, base_path=None):
        app_audio_root = os.environ.get("APP_AUDIO_ROOT", "/backend/app/audio_dumps")
        default_base = os.path.join(app_audio_root, "archiver")

        self.base_path = os.environ.get("AUDIO_ARCHIVE_PATH") or base_path or default_base
        self.queue = asyncio.Queue()
        self.running = True
        self._buffers = defaultdict(lambda: {"raw": bytearray(), "processed": bytearray(), "start_time": time.time()})
        self._worker_task = None
        
        # Garantir diretório base
        os.makedirs(self.base_path, exist_ok=True)

    def start(self):
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"AudioArchiver iniciado. Caminho: {self.base_path}")

    async def stop(self):
        self.running = False
        await self.queue.put(None) # Sentinel
        if self._worker_task:
            await self._worker_task

    def archive_chunk(self, balcao_id: str, pcm_chunk: bytes, is_processed: bool = False):
        """Método síncrono para adicionar um chunk na fila de processamento."""
        try:
            self.queue.put_nowait((balcao_id, pcm_chunk, is_processed, time.time()))
        except asyncio.QueueFull:
            logger.warning("Fila do AudioArchiver cheia! Descartando chunk.")

    async def _worker(self):
        while self.running or not self.queue.empty():
            item = await self.queue.get()
            if item is None:
                break
            
            balcao_id, chunk, is_processed, ts = item
            
            buf = self._buffers[balcao_id]
            key = "processed" if is_processed else "raw"
            buf[key].extend(chunk)
            
            # Se passou 60 segundos desde o início deste buffer, salva
            if ts - buf["start_time"] >= 60:
                await self._save_segment(balcao_id)
                # Reset buffer
                self._buffers[balcao_id] = {"raw": bytearray(), "processed": bytearray(), "start_time": time.time()}
            
            self.queue.task_done()

    async def _save_segment(self, balcao_id: str):
        buf = self._buffers[balcao_id]
        if not buf["raw"] and not buf["processed"]:
            return

        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H%M%S")
        
        dir_path = os.path.join(self.base_path, date_str, balcao_id)
        os.makedirs(dir_path, exist_ok=True)

        # Salvar RAW
        if buf["raw"]:
            filename = f"raw_{time_str}.wav"
            filepath = os.path.join(dir_path, filename)
            await asyncio.to_thread(self._write_wav, filepath, buf["raw"])

        # Salvar PROCESSED
        if buf["processed"]:
            filename = f"processed_{time_str}.wav"
            filepath = os.path.join(dir_path, filename)
            await asyncio.to_thread(self._write_wav, filepath, buf["processed"])

    def _write_wav(self, path: str, pcm_data: bytes, sample_rate: int = 16000):
        try:
            with wave.open(path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2) # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_data)
        except Exception as e:
            logger.error(f"Erro ao salvar WAV {path}: {e}")

    def save_interaction_audio(self, balcao_id: str, pcm_data: bytes, interaction_id: int) -> str:
        """
        Salva um áudio de uma interação específica e retorna o caminho relativo.
        Usado para associar o áudio bruto à interação no banco, agora contendo o ID real.
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        # Subpasta por data e balcão
        rel_dir = os.path.join(date_str, balcao_id)
        abs_dir = os.path.join(self.base_path, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        
        # Usa o ID retornado do banco de dados na nomenclatura
        filename = f"interaction_{interaction_id}.wav"
        filepath = os.path.join(abs_dir, filename)
        
        self._write_wav(filepath, pcm_data)
        
        # Retorna o caminho relativo (ex: 2024-05-20/balcao_1/interaction_123.wav)
        return os.path.join(rel_dir, filename)

# Instância Global
archiver = AudioArchiver()
