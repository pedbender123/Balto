import os
import sys
import wave
import csv
import time
import numpy as np
from datetime import datetime

# Adicionar parent dir ao path para importar app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import audio_processor, vad, transcription

# Configurações
BASE_DIR = os.path.dirname(__file__)
INPUT_DIR = os.path.join(BASE_DIR, 'audios_brutos')
OUTPUT_SEGMENTS_DIR = os.path.join(BASE_DIR, 'trechos_fala')
REPORT_FILE = os.path.join(BASE_DIR, 'relatorio_comparativo.csv')

import subprocess

def decode_audio_to_pcm(file_path):
    """Decodifica áudio (wav/webm) para PCM 16-bit 16kHz Mono usando FFmpeg."""
    try:
        cmd = [
            "ffmpeg", "-i", file_path,
            "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000",
            "-loglevel", "error", "-"
        ]
        # Executa e pega todo o output
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return process.stdout
    except Exception as e:
        print(f"Erro FFmpeg ao decodificar {file_path}: {e}")
        return None

import json

# Configurações Adicionais
STATUS_FILE = os.path.join(BASE_DIR, '..', 'app', 'static', 'batch_status.json')

def update_status(data):
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def run_comparison_report():
    print("--- Iniciando Geração de Relatório Comparativo ---")
    
    # Garantir diretórios
    os.makedirs(OUTPUT_SEGMENTS_DIR, exist_ok=True)
    
    # Preparar CSV
    file_exists = os.path.isfile(REPORT_FILE)
    csv_header = [
        "Arquivo_Original", "Transcricao_Original_Full", 
        "Segmento_ID", "Duracao_Segundos", "SNR_dB",
        "System_Choice_Model", "System_Choice_Reason",
        "Transcricao_Segmento_ElevenLabs", "Transcricao_Segmento_AssemblyAI",
        "Acuracia_Manual" # Campo para preenchimento humano
    ]
    
    # Abrir CSV para append ou write
    mode = 'a' if file_exists else 'w'
    with open(REPORT_FILE, mode, newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(csv_header)
            
        files = sorted([f for f in os.listdir(INPUT_DIR) if f.endswith('.wav') or f.endswith('.webm')])
        total_files = len(files)
        
        if not files:
            print("Nenhum arquivo de áudio encontrado em audios_brutos.")
            return

        print(f"Encontrados {len(files)} arquivos.")

        for idx, file_name in enumerate(files):
            # Update Status for UI
            update_status({
                "total": total_files,
                "current": idx + 1,
                "percent": int(((idx + 1) / total_files) * 100),
                "current_file": file_name,
                "status": "processing"
            })
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processando: {file_name}")
            file_path = os.path.join(INPUT_DIR, file_name)
            
            # 1. Carregar Áudio Original Completo (Bytes crus do arquivo para ElevenLabs)
            try:
                with open(file_path, 'rb') as f:
                    full_file_bytes = f.read()
            except Exception as e:
                print(f"Erro ao ler arquivo {file_name}: {e}")
                continue

            # 2. Transcrever Original
            print("   -> Transcrevendo arquivo completo (Reference)...")
            original_transcription = transcription.transcrever_elevenlabs(full_file_bytes)
            print(f"      Original: {original_transcription[:50]}...")
            
            # 3. Processamento de Stream (Simulação)
            # Decodificar para PCM 16k para VAD/Cleaning
            pcm_bytes = decode_audio_to_pcm(file_path)
            if not pcm_bytes:
                print("   -> Falha na decodificação PCM. Pulando.")
                continue
                
            # Inicializar processadores
            cleaner = audio_processor.AudioCleaner()
            vad_session = vad.VAD()
            
            # Simular chunks
            frames_per_chunk = 480 # 30ms (480 samples * 2 bytes = 960 bytes)
            chunk_size_bytes = frames_per_chunk * 2 
            
            segment_counter = 0
            offset = 0
            total_bytes = len(pcm_bytes)
            
            while offset < total_bytes:
                chunk = pcm_bytes[offset : offset + chunk_size_bytes]
                offset += chunk_size_bytes
                
                if not chunk: break
                
                # Clean
                cleaned_chunk = cleaner.process(chunk)
                
                # VAD
                speech_segment = vad_session.process(cleaned_chunk)
                
                if speech_segment:
                    segment_counter += 1
                    
                    # Calcular duração antes para usar no nome
                    duracao = len(speech_segment) / 32000.0
                    
                    # Nome solicitado
                    clean_filename = os.path.splitext(file_name)[0].replace(" ", "_")
                    seg_name = f"{duracao:.2f}s_speech_seg_{clean_filename}_{segment_counter:03d}.wav"
                    seg_path = os.path.join(OUTPUT_SEGMENTS_DIR, seg_name)
                    
                    # Salvar Segmento
                    with wave.open(seg_path, 'wb') as seg_wf:
                        seg_wf.setnchannels(1)
                        seg_wf.setsampwidth(2)
                        seg_wf.setframerate(16000)
                        seg_wf.writeframes(speech_segment)
                    
                    # 4. Processar Segmento (Comparação)
                    snr = transcription.calcular_snr(speech_segment)
                    
                    print(f"      Seg {segment_counter}: {duracao:.2f}s, SNR: {snr:.2f}dB, Arquivo: {seg_name}")
                    
                    # Decisão do Sistema
                    usar_economico = (snr > 15.0) and (duracao < 5.0)
                    system_choice = "AssemblyAI" if usar_economico else "ElevenLabs"
                    reason = "HighSNR+Short" if usar_economico else "LowSNR_or_Long"
                    
                    # Transcrever com AMBOS
                    print("         -> Transcrevendo ElevenLabs...")
                    txt_eleven = transcription.transcrever_elevenlabs(speech_segment)
                    
                    print("         -> Transcrevendo AssemblyAI...")
                    txt_assembly = transcription.transcrever_assemblyai(speech_segment)
                    
                    # Gravar no CSV
                    writer.writerow([
                        file_name,
                        original_transcription,
                        seg_name,
                        f"{duracao:.2f}",
                        f"{snr:.2f}",
                        system_choice,
                        reason,
                        txt_eleven,
                        txt_assembly,
                        "" # Acuracia Manual em branco
                    ])
                    csvfile.flush()
                    
            print(f"   -> Finalizado {file_name}. {segment_counter} segmentos.")

    # Status Final
    update_status({"percent": 100, "status": "done", "current_file": "Concluído"})
    print(f"\nRelatório gerado em: {REPORT_FILE}")

if __name__ == "__main__":
    run_comparison_report()
