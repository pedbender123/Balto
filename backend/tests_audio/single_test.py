import os
import sys
import subprocess
from dotenv import load_dotenv

# Setup paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # backend/tests_audio
BACKEND_DIR = os.path.dirname(BASE_DIR) # backend
sys.path.append(BACKEND_DIR)

# Load Env
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

from app.transcription import transcrever_elevenlabs, transcrever_assemblyai, key_manager

TEST_FILE = os.path.join(BASE_DIR, "audios_brutos", "10_20250907210004.webm")
TEMP_WAV = os.path.join(BASE_DIR, "temp_test.wav")

import imageio_ffmpeg

def convert_to_wav():
    print(f"--- Convertendo {TEST_FILE} para WAV ---")
    if os.path.exists(TEMP_WAV):
        os.remove(TEMP_WAV)
    
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    cmd = [
        ffmpeg_exe, "-i", TEST_FILE,
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        TEMP_WAV, "-y"
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if os.path.exists(TEMP_WAV):
        print("conversão OK.")
        return True
    else:
        print("Falha na conversão.")
        return False

def run_test():
    if not convert_to_wav():
        return

    with open(TEMP_WAV, "rb") as f:
        audio_data = f.read()
    
    print(f"Áudio carregado: {len(audio_data)} bytes (WAV PCM 16kHz)")

    # 1. Testar AssemblyAI
    print("\n--- Testando AssemblyAI ---")
    try:
        res_assembly = transcrever_assemblyai(audio_data)
        print(f"Resultado AssemblyAI: '{res_assembly}'")
    except Exception as e:
        print(f"Erro AssemblyAI: {e}")

    # 2. Testar ElevenLabs
    print("\n--- Testando ElevenLabs ---")
    try:
        # ElevenLabs transcription function expects bytes. 
        # Inside it creates a BytesIO named 'audio.wav'.
        # Since we are passing WAV bytes, it should be perfect.
        res_eleven = transcrever_elevenlabs(audio_data)
        print(f"Resultado ElevenLabs: '{res_eleven}'")
    except Exception as e:
        print(f"Erro ElevenLabs: {e}")

if __name__ == "__main__":
    run_test()
