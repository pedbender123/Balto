import os
import sys
import wave
import csv
import json
import subprocess
import numpy as np
import torch
from datetime import datetime

# ============================================================================
# SETUP AMBIENTE
# ============================================================================
# Adiciona o diretório 'backend' ao path para importar 'app'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))
if BACKEND_DIR not in sys.path:
    sys.path.append(BACKEND_DIR)

# Importações do App (Core Logic)
try:
    from app import silero_vad, transcription, audio_processor
except ImportError as e:
    print(f"ERRO DE IMPORTAÇÃO: Não foi possível importar módulos do app: {e}")
    print(f"Certifique-se de estar rodando este script da raiz do projeto ou que 'app' esteja acessível.")
    print(f"PYTHONPATH atual: {sys.path}")
    sys.exit(1)

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================
INPUT_DIR = os.path.join(BASE_DIR, 'audios_brutos')
OUTPUT_SEGMENTS_DIR = os.path.join(BASE_DIR, 'trechos_fala')
REPORT_FILE = os.path.join(BASE_DIR, 'relatorio_comparativo.csv')
STATUS_FILE = os.path.join(BACKEND_DIR, 'app', 'static', 'batch_status.json')

# Configuração de Áudio (Chunks)
CLEANER_CHUNK_SIZE = 1536  # 96ms (3 * 512)
VAD_CHUNK_SIZE = 512       # 32ms (Requisito Silero)

def decode_audio_stream(file_path):
    """
    Decodifica áudio para PCM s16le 16kHz Mono usando FFmpeg via PIPE.
    """
    try:
        cmd = [
            "ffmpeg", "-i", file_path,
            "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000",
            "-loglevel", "error", "-"
        ]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return process
    except Exception as e:
        print(f"Erro ao iniciar FFmpeg para {file_path}: {e}")
        return None

def update_status(data):
    """Atualiza arquivo JSON para frontend acompanhar progresso (opcional)."""
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, 'w') as f:
            json.dump(data, f)
    except:
        pass

def main():
    print("=== Gerador de Relatório de Áudio (Simplificado) ===")
    print(f"Diretório de Entrada: {INPUT_DIR}")
    print(f"Saída: {REPORT_FILE}")

    # 1. Preparação
    os.makedirs(OUTPUT_SEGMENTS_DIR, exist_ok=True)
    os.makedirs(INPUT_DIR, exist_ok=True) # Garante que existe para evitar erro
    
    # Criar/Resetar CSV
    headers = [
        "Arquivo_Original", "Transcricao_Original_Full", 
        "Segmento_ID", "Duracao_Segundos", "SNR_dB",
        "System_Choice", "System_Reason",
        "Txt_ElevenLabs", "Txt_AssemblyAI"
    ]
    with open(REPORT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

    # 2. Listar Arquivos
    files = sorted([f for f in os.listdir(INPUT_DIR) if f.endswith(('.wav', '.webm', '.mp3'))])
    total = len(files)
    
    if total == 0:
        print("Nenhum arquivo encontrado em 'audios_brutos'.")
        print("Por favor, coloque arquivos .wav ou .webm nesta pasta e tente novamente.")
        return

    # 3. Inicializar Modelos
    print("Carregando VAD (Silero)...")
    vad = silero_vad.SileroVAD(threshold=0.5)
    vad_iterator = vad.get_iterator()
    cleaner = audio_processor.AudioCleaner()

    # 4. Loop Principal
    for i, fname in enumerate(files):
        print(f"\n[{i+1}/{total}] Processando: {fname}")
        fpath = os.path.join(INPUT_DIR, fname)
        
        # Feedback Visual
        update_status({
            "total": total, "current": i+1, "percent": int(((i+1)/total)*100),
            "current_file": fname, "status": "processing"
        })

        # --- A. Transcrição de Referência (ElevenLabs Full) ---
        original_text = ""
        try:
            # Lemos o arquivo bruto em memória para enviar para ElevenLabs
            # (ElevenLabs aceita formatos comprimidos, então mandamos o arquivo original)
            with open(fpath, 'rb') as f_in:
                raw_bytes = f_in.read()
            
            print("   -> Transcrevendo arquivo completo (Ref)...")
            original_text = transcription.transcrever_elevenlabs(raw_bytes)
            print(f"      Ref: {original_text[:60]}...")
        except Exception as e:
            print(f"      [Erro Ref]: {e}")
            original_text = "ERROR"

        # --- B. Processamento Stream (Clean -> VAD -> Split) ---
        process = decode_audio_stream(fpath)
        if not process: continue

        buffer_fala = []
        is_speaking = False
        seg_count = 0
        
        while True:
            # Ler chunk para Cleaner
            chunk_bytes = process.stdout.read(CLEANER_CHUNK_SIZE * 2)
            if not chunk_bytes: break

            # Limpar
            cleaned = cleaner.process(chunk_bytes)

            # Iterar sub-chunks para VAD
            offset = 0
            while offset < len(cleaned):
                vad_chunk = cleaned[offset : offset + VAD_CHUNK_SIZE * 2]
                offset += VAD_CHUNK_SIZE * 2
                
                if len(vad_chunk) < VAD_CHUNK_SIZE * 2: continue # Ignora resto final indevido

                # VAD Check
                # Convert bytes -> float32 tensor
                flt = np.frombuffer(vad_chunk, dtype=np.int16).astype(np.float32) / 32768.0
                tensor = torch.Tensor(flt)
                
                speech_dict = vad_iterator(tensor, return_seconds=False)

                if speech_dict:
                    if 'start' in speech_dict:
                        is_speaking = True
                        buffer_fala.append(vad_chunk)
                    elif 'end' in speech_dict:
                        is_speaking = False
                        buffer_fala.append(vad_chunk)
                        
                        # --- C. Finalizou Segmento ---
                        seg_audio = b''.join(buffer_fala)
                        buffer_fala = []
                        
                        # Filtro de Duração (> 0.5s)
                        if len(seg_audio) > (16000 * 2 * 0.5):
                            seg_count += 1
                            dur_sec = len(seg_audio) / 32000.0
                            
                            # Salvar
                            clean_name = os.path.splitext(fname)[0].replace(' ', '_')
                            seg_fname = f"{dur_sec:.2f}s_seg_{clean_name}_{seg_count:02d}.wav"
                            seg_fpath = os.path.join(OUTPUT_SEGMENTS_DIR, seg_fname)
                            
                            with wave.open(seg_fpath, 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(16000)
                                wf.writeframes(seg_audio)
                            
                            # Análise
                            snr = transcription.calcular_snr(seg_audio)
                            
                            # Lógica Inteligente (Simulada)
                            # > 15dB e < 5s => AssemblyAI (Economico)
                            use_cheap = (snr > 15.0) and (dur_sec < 5.0)
                            choice = "AssemblyAI" if use_cheap else "ElevenLabs"
                            reason = "HighSNR+Short" if use_cheap else "Complex"
                            
                            print(f"      Seg {seg_count}: {dur_sec:.2f}s | SNR: {snr:.1f}dB | -> {choice}")
                            
                            # Transcrições (AMBAS)
                            txt_11 = transcription.transcrever_elevenlabs(seg_audio)
                            txt_aa = transcription.transcrever_assemblyai(seg_audio)
                            
                            # CSV
                            with open(REPORT_FILE, 'a', newline='', encoding='utf-8') as f:
                                w = csv.writer(f)
                                w.writerow([
                                    fname, original_text, 
                                    seg_fname, f"{dur_sec:.2f}", f"{snr:.1f}",
                                    choice, reason,
                                    txt_11, txt_aa
                                ])

                else:
                    if is_speaking:
                        buffer_fala.append(vad_chunk)
        
        # Reset VAD state após cada arquivo
        vad.model.reset_states()
        vad_iterator = vad.get_iterator()
        
    print("\n=== Processamento Concluído ===")
    print(f"Relatório salvo em: {REPORT_FILE}")
    update_status({"percent": 100, "status": "done", "current_file": "Concluído"})

if __name__ == "__main__":
    main()
