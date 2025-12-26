import torch
import os
import sys
import wave
import csv
import time
import numpy as np
from datetime import datetime

# Adicionar parent dir ao path para importar app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import silero_vad, transcription, audio_processor

# Configurações
BASE_DIR = os.path.dirname(__file__)
INPUT_DIR = os.path.join(BASE_DIR, 'audios_brutos')
OUTPUT_SEGMENTS_DIR = os.path.join(BASE_DIR, 'trechos_fala')
REPORT_FILE = os.path.join(BASE_DIR, 'relatorio_comparativo.csv')

import subprocess
import json

# Configurações Adicionais
STATUS_FILE = os.path.join(BASE_DIR, '..', 'app', 'static', 'batch_status.json')
# Configuração de Chunks
CLEANER_CHUNK_SIZE = 1536 # 96ms (3 * 512) - Suficiente para n_fft=1024
VAD_CHUNK_SIZE = 512 # 32ms - Requisito Silero

def update_status(data):
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def convert_to_stream(file_path):
    """Gera chunks de 512 samples (16k) usando FFmpeg."""
    try:
        cmd = [
            "ffmpeg", "-i", file_path,
            "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000",
            "-loglevel", "error", "-"
        ]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return process
    except Exception as e:
        print(f"Erro FFmpeg: {e}")
        return None

def run_comparison_report():
    print("--- Iniciando Geração de Relatório Comparativo (Silero VAD) ---")
    
    # Garantir diretórios
    os.makedirs(OUTPUT_SEGMENTS_DIR, exist_ok=True)
    
    # Preparar CSV (Preservar cabeçalho se existir? Não, vamos resetar pra garantir colunas certas)
    csv_header = [
        "Arquivo_Original", "Transcricao_Original_Full", 
        "Segmento_ID", "Duracao_Segundos", "SNR_dB",
        "System_Choice_Model", "System_Choice_Reason",
        "Transcricao_Segmento_ElevenLabs", "Transcricao_Segmento_AssemblyAI",
        "Acuracia_Manual" 
    ]
    
    with open(REPORT_FILE, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(csv_header)
            
        files = sorted([f for f in os.listdir(INPUT_DIR) if f.endswith('.wav') or f.endswith('.webm')])
        total_files = len(files)
        
        if not files:
            print("Nenhum arquivo de áudio encontrado em audios_brutos.")
            return

        print(f"Encontrados {len(files)} arquivos.")
        
        # Inicializa Silero
        print("Carregando Silero VAD...")
        vad = silero_vad.SileroVAD(threshold=0.5)
        vad_iterator = vad.get_iterator()

        for idx, file_name in enumerate(files):
            update_status({
                "total": total_files,
                "current": idx + 1,
                "percent": int(((idx + 1) / total_files) * 100),
                "current_file": file_name,
                "status": "processing"
            })
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processando: {file_name}")
            file_path = os.path.join(INPUT_DIR, file_name)
            
            # 1. Transcrever Original (ElevenLabs)
            try:
                with open(file_path, 'rb') as f:
                    full_file_bytes = f.read()
                print("   -> Transcrevendo arquivo completo (Reference)...")
                original_transcription = transcription.transcrever_elevenlabs(full_file_bytes)
                print(f"      Original: {original_transcription[:50]}...")
            except Exception as e:
                print(f"Erro ao ler/transcrever original {file_name}: {e}")
                original_transcription = "ERROR"
            
            # 2. Processamento Stream (Silero Logic)
            process = convert_to_stream(file_path)
            if not process: continue
            
            current_speech_buffer = []
            segment_counter = 0
            is_speaking = False
            
            cleaner_inst = audio_processor.AudioCleaner()
            
            while True:
                # Ler chunk MAIOR para o Cleaner (1536 samples * 2 = 3072 bytes)
                cleaner_bytes_req = CLEANER_CHUNK_SIZE * 2
                raw_bytes = process.stdout.read(cleaner_bytes_req)
                
                if not raw_bytes: break
                
                # Clean
                cleaned_bytes = cleaner_inst.process(raw_bytes)
                
                # Fatiar para o VAD (chunks de 512 samples = 1024 bytes)
                vad_bytes_req = VAD_CHUNK_SIZE * 2
                offset = 0
                
                while offset < len(cleaned_bytes):
                    # Pegar sub-chunk
                    vad_chunk_bytes = cleaned_bytes[offset : offset + vad_bytes_req]
                    offset += vad_bytes_req
                    
                    # Se sobrar pedaço (no final do arquivo), ignorar ou padding? Silero precisa de 512.
                    if len(vad_chunk_bytes) < vad_bytes_req:
                        continue 
                        
                    # Prep Tensor
                    audio_int16 = np.frombuffer(vad_chunk_bytes, dtype=np.int16)
                    audio_float32 = audio_int16.astype(np.float32) / 32768.0
                    tensor_chunk = torch.Tensor(audio_float32)
    
                    # VAD Step
                    speech_dict = vad_iterator(tensor_chunk, return_seconds=False)
                    
                    if speech_dict:
                        if 'start' in speech_dict:
                            is_speaking = True
                            current_speech_buffer.append(vad_chunk_bytes)
                        elif 'end' in speech_dict:
                            is_speaking = False
                            current_speech_buffer.append(vad_chunk_bytes)
                            
                            # Processar Segmento Completo
                            full_audio = b''.join(current_speech_buffer)
                            current_speech_buffer = []
                            
                            # Filtro Curto (< 0.5s ignora)
                            if len(full_audio) > 16000:
                                segment_counter += 1
                                duracao = len(full_audio) / 32000.0
                                
                                # Clean Name
                                clean_fn = os.path.splitext(file_name)[0].replace(" ", "_")
                                seg_name = f"{duracao:.2f}s_speech_seg_{clean_fn}_{segment_counter:03d}.wav"
                                seg_path = os.path.join(OUTPUT_SEGMENTS_DIR, seg_name)
                                
                                # Salvar
                                with wave.open(seg_path, 'wb') as wf:
                                    wf.setnchannels(1)
                                    wf.setsampwidth(2)
                                    wf.setframerate(16000)
                                    wf.writeframes(full_audio)
                                
                                # Analisar e Transcrever
                                snr = transcription.calcular_snr(full_audio)
                                usar_economico = (snr > 15.0) and (duracao < 5.0)
                                sys_choice = "AssemblyAI" if usar_economico else "ElevenLabs"
                                reason = "HighSNR+Short" if usar_economico else "LowSNR_or_Long"
                                
                                print(f"      Seg {segment_counter}: {duracao:.2f}s, SNR: {snr:.2f}dB -> {sys_choice}")
                                
                                # Transcrições
                                txt_eleven = transcription.transcrever_elevenlabs(full_audio)
                                txt_assembly = transcription.transcrever_assemblyai(full_audio)
                                
                                # CSV Write
                                writer.writerow([
                                    file_name,
                                    original_transcription,
                                    seg_name,
                                    f"{duracao:.2f}",
                                    f"{snr:.2f}",
                                    sys_choice,
                                    reason,
                                    txt_eleven,
                                    txt_assembly,
                                    ""
                                ])
                                csvfile.flush()
                    else:
                        if is_speaking:
                            current_speech_buffer.append(vad_chunk_bytes)
            
            # Reset VAD state between files? 
            # batch_process_audio explicitly says NO, to keep continuity if strictly streaming.
            # But files are distinct here. Resetting is safer for independent files.
            vad.model.reset_states()
            vad_iterator = vad.get_iterator()
            
            print(f"   -> Finalizado {file_name}. {segment_counter} segmentos.")

    # Status Final
    update_status({"percent": 100, "status": "done", "current_file": "Concluído"})
    print(f"\nRelatório gerado em: {REPORT_FILE}")

if __name__ == "__main__":
    run_comparison_report()
