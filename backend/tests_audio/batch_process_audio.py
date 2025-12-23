import os
import sys
import subprocess
import wave
import json
import torch
import numpy as np

# Adicionar o diretório pai ao path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import silero_vad

# Configurações
STATUS_FILE = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'batch_status.json')
AUDIO_DIR = os.path.join(os.path.dirname(__file__), 'audios_brutos')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'trechos_fala')
SAMPLE_RATE = 16000
CHUNK_SIZE = 512 # Recomendado para Silero (32ms em 16kHz)

def update_status(data):
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def convert_webm_stream(input_path):
    """Gera chunks de bytes (PCM 16le 16kHz) a partir de um arquivo usando ffmpeg."""
    cmd = [
        "ffmpeg", "-i", input_path,
        "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000",
        "-loglevel", "error", "-"
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    while True:
        # Lê EXATAMENTE 1024 bytes (512 samples de 2 bytes)
        # Necessário para o Silero aceitar o tensor flat correto
        chunk = process.stdout.read(CHUNK_SIZE * 2)
        if not chunk:
            break
        yield chunk
        
    process.wait()

def batch_process_streaming():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. Carregar Modelo
    print("--- Inicializando Silero VAD ---")
    vad = silero_vad.SileroVAD(threshold=0.5) 
    vad_iterator = vad.get_iterator()
    
    # 2. Listar Arquivos
    files = sorted([f for f in os.listdir(AUDIO_DIR) if f.endswith('.webm')])
    total_files = len(files)
    
    print(f"--- Iniciando processamento contínuo de {total_files} arquivos ---")
    
    current_speech_buffer = [] # Lista de chunks (bytes)
    segment_count = 0
    is_speaking = False
    
    for idx, file_name in enumerate(files):
        # Update Status
        update_status({
            "total": total_files,
            "current": idx + 1,
            "percent": int(((idx + 1) / total_files) * 100),
            "current_file": file_name,
            "status": "processing"
        })
        print(f"[{idx+1}/{total_files}] Lendo: {file_name}")
        
        input_path = os.path.join(AUDIO_DIR, file_name)
        
        # Generator de chunks do arquivo atual
        stream = convert_webm_stream(input_path)
        
        for pcm_bytes in stream:
            if len(pcm_bytes) != CHUNK_SIZE * 2:
                continue # Pula chunks quebrados (final de arquivo)
                
            # Converter para Tensor float32
            # Copiar bytes para evitar erro de buffer não alinhado ou negativo striding
            audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
            
            # Normalização (int16 -> float32 -1..1)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            tensor_chunk = torch.Tensor(audio_float32)
            
            # Reset de estado não é chamado entre arquivos propositalmente para manter contiguidade
            
            # Processar no VAD
            speech_dict = vad_iterator(tensor_chunk, return_seconds=False)
            
            if speech_dict:
                if 'start' in speech_dict:
                    # Início de fala detectado
                    # print("   >>> Fala iniciada")
                    is_speaking = True
                    current_speech_buffer.append(pcm_bytes)
                    
                elif 'end' in speech_dict:
                    # Fim de fala detectado
                    # print("   <<< Fala encerrada")
                    is_speaking = False
                    current_speech_buffer.append(pcm_bytes)
                    
                    # Salvar Segmento
                    full_audio = b''.join(current_speech_buffer)
                    
                    # Filtro de Duração (Ex: descartar < 0.5s)
                    if len(full_audio) > 16000: # > 0.5s
                        segment_count += 1
                        out_name = f"speech_seg_{segment_count:03d}.wav"
                        out_path = os.path.join(OUTPUT_DIR, out_name)
                        
                        with wave.open(out_path, 'wb') as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(SAMPLE_RATE)
                            wf.writeframes(full_audio)
                        
                        # print(f"      Salvo: {out_name} ({len(full_audio)/32000:.2f}s)")
                        
                    current_speech_buffer = []
            else:
                # Se não houve evento, mas estamos falando, acumula
                if is_speaking:
                    current_speech_buffer.append(pcm_bytes)
                    
    update_status({"percent": 100, "status": "done", "current_file": "Concluído"})
    print(f"\n--- Processamento Finalizado. {segment_count} segmentos gerados. ---")

if __name__ == "__main__":
    batch_process_streaming()
