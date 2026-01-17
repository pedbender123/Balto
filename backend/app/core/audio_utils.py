
import subprocess
import os
import wave
import uuid
import imageio_ffmpeg
from datetime import datetime
from app.core import config

def decode_webm_to_pcm16le(webm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Decodifica WebM/Opus para PCM 16-bit 16kHz usando FFmpeg."""
    try:
        ffmpeg_cmd = imageio_ffmpeg.get_ffmpeg_exe()
        proc = subprocess.run(
            [
                ffmpeg_cmd, "-i", "pipe:0", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
                "pipe:1", "-loglevel", "error"
            ],
            input=webm_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            print(f"[FFMPEG] Erro: {proc.stderr.decode('utf-8')}")
            return b""
        return proc.stdout
    except Exception as e:
        print(f"[FFMPEG] Exception: {e}")
        return b""

def dump_audio_to_disk(audio_bytes: bytes, balcao_id: str):
    """Salva o áudio bruto para análise (Fase 1.2)."""
    if not os.path.exists(config.AUDIO_DUMP_DIR):
        os.makedirs(config.AUDIO_DUMP_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{balcao_id}_{timestamp}_{uuid.uuid4().hex[:6]}.wav"
    filepath = os.path.join(config.AUDIO_DUMP_DIR, filename)
    
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_bytes)
    print(f"[DUMP] Áudio salvo: {filepath}")
