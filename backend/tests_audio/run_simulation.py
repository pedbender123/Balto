import os
import sys
import wave
import time
from datetime import datetime
import numpy as np

# Adicionar o diretório pai ao path para importar 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import audio_processor, vad

def run_simulation():
    """
    Simula o processamento de áudio em tempo real lendo arquivos wav.
    """
    base_dir = os.path.dirname(__file__)
    input_dir = os.path.join(base_dir, 'audios_brutos')
    clean_dir = os.path.join(base_dir, 'audios_limpos')
    segments_dir = os.path.join(base_dir, 'trechos_fala')

    # Garantir que diretórios existam
    os.makedirs(clean_dir, exist_ok=True)
    os.makedirs(segments_dir, exist_ok=True)

    files = [f for f in os.listdir(input_dir) if f.endswith('.wav')]
    if not files:
        print(f"Nenhum arquivo .wav encontrado em {input_dir}")
        print("Adicione arquivos para teste.")
        return

    print(f"Encontrados {len(files)} arquivos para processar.")

    for file_name in files:
        input_path = os.path.join(input_dir, file_name)
        print(f"\n--- Processando: {file_name} ---")

        # Inicializar processadores
        cleaner = audio_processor.AudioCleaner()
        vad_session = vad.VAD()

        # Buffers output
        full_cleaned_audio = bytearray()
        
        # Abrir arquivo wav
        with wave.open(input_path, 'rb') as wf:
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
                print(f"Skipping {file_name}: Formato inválido. Requer mono, 16bit, 16kHz.")
                continue
            
            chunk_size = 320 # 20ms a 16kHz (16000 * 0.02 * 2 bytes = 640 bytes? Não, readframes lê frames, um frame 16bit mono é 2 bytes. 16000 frames/s. 20ms = 320 frames.)
            # VAD usa 30ms normalmente no meu código? Deixe-me checar vad.py
            # vad.py __init__ default frame_duration_ms=30.
            # 30ms * 16000 / 1000 = 480 frames. 
            
            # Vamos ler em chunks pequenos para simular stream. O VAD bufferiza internamente.
            # Se lermos 480 frames (30ms), bate com o default do VAD que é frame_duration_ms=30 (vad.py:16).
            # O VAD.process espera bytes.
            frames_per_chunk = 480 

            segment_counter = 0

            while True:
                data = wf.readframes(frames_per_chunk)
                if not data:
                    break
                
                # 1. Limpeza
                cleaned_chunk = cleaner.process(data)
                full_cleaned_audio.extend(cleaned_chunk)

                # 2. VAD
                # O VAD retorna bytes SE completou um segmento de fala, senão None
                speech_segment = vad_session.process(cleaned_chunk)

                if speech_segment:
                    segment_counter += 1
                    seg_name = f"{os.path.splitext(file_name)[0]}_seg_{segment_counter:02d}.wav"
                    seg_path = os.path.join(segments_dir, seg_name)
                    
                    with wave.open(seg_path, 'wb') as seg_wf:
                        seg_wf.setnchannels(1)
                        seg_wf.setsampwidth(2)
                        seg_wf.setframerate(16000)
                        seg_wf.writeframes(speech_segment)
                    
                    print(f"   -> Voz detectada: {seg_name} ({len(speech_segment)} bytes)")

        # Salvar áudio limpo completo
        clean_name = f"clean_{file_name}"
        clean_path = os.path.join(clean_dir, clean_name)
        with wave.open(clean_path, 'wb') as clean_wf:
            clean_wf.setnchannels(1)
            clean_wf.setsampwidth(2)
            clean_wf.setframerate(16000)
            clean_wf.writeframes(full_cleaned_audio)
        
        print(f"Processamento concluído. Limpo salvo em: {clean_name}")

if __name__ == "__main__":
    run_simulation()
