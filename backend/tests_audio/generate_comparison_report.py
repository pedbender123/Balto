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
        if not files:
            print("Nenhum arquivo de áudio encontrado em audios_brutos.")
            return

        print(f"Encontrados {len(files)} arquivos.")

        for file_name in files:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Processando: {file_name}")
            file_path = os.path.join(INPUT_DIR, file_name)
            
            # 1. Carregar Áudio Original Completo
            try:
                # Ler arquivo completo como bytes
                with open(file_path, 'rb') as f:
                    full_audio_bytes = f.read()
            except Exception as e:
                print(f"Erro ao ler arquivo {file_name}: {e}")
                continue

            # 2. Transcrever Original (ElevenLabs) - Apenas uma vez por arquivo
            # Nota: Isso pode gastar bastante quota se os arquivos forem grandes.
            print("   -> Transcrevendo arquivo completo (Reference)...")
            # Para o report, precisamos converter webm para wav se for o caso, 
            # mas a função transcrever_elevenlabs espera bytes e o serviço suporta varios formatos,
            # porém nossa função interna wrapa em 'audio.wav'.
            # Se o input é .webm, o header estar errado pode dar ruim no ElevenLabs se a extensão for .wav
            # Idealmente deveriamos converter pra wav antes.
            # O script batch_process_audio.py usa ffmpeg. Vamos assumir que aqui os inputs são .wav 
            # (conforme run_simulation.py) ou se for webm, o ffmpeg converte.
            # Vamos simplificar: se for .wav, manda bala.
            
            original_transcription = transcription.transcrever_elevenlabs(full_audio_bytes)
            print(f"      Original: {original_transcription[:50]}...")
            
            # 3. Processamento de Stream (Simulação)
            # Precisamos simular o VAD e Split
            
            # Inicializar processadores
            cleaner = audio_processor.AudioCleaner()
            vad_session = vad.VAD()
            
            # Ler áudio frame a frame (como em run_simulation.py)
            try:
                wf = wave.open(file_path, 'rb')
            except:
                # Se falhar wave.open (ex: webm), vamos pular por enquanto ou exigir wav
                # O run_simulation.py exigia wav. Vamos manter exigencia ou usar ffmpeg se precisarmos.
                # O user falou "audios saindo o trecho...".
                print("   -> Arquivo não é WAV padrão ou erro ao abrir. Pulando simulação de segmentos.")
                continue

            if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
                 print("   -> Formato inválido (requer WAV Mono 16kHz).")
                 continue
                 
            frames_per_chunk = 480 # 30ms
            segment_counter = 0
            
            while True:
                data = wf.readframes(frames_per_chunk)
                if not data: break
                
                # Clean
                cleaned_chunk = cleaner.process(data)
                
                # VAD
                speech_segment = vad_session.process(cleaned_chunk)
                
                if speech_segment:
                    segment_counter += 1
                    
                    # Calcular duração antes para usar no nome
                    duracao = len(speech_segment) / 32000.0
                    
                    # Nome solicitado: QNT_SEGUNDOS_speech_seg_ARQUIVO_ORIGINAL
                    # Adicionamos contador para garantir unicidade se houver multiplos segmentos
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
                    # Usando lógica do transcrever_inteligente mas sem chamar a transcrição ainda para não gastar duplo
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
                    csvfile.flush() # Garantir gravação
                    
            wf.close()
            print(f"   -> Finalizado {file_name}. {segment_counter} segmentos.")

    print(f"\nRelatório gerado em: {REPORT_FILE}")

if __name__ == "__main__":
    run_comparison_report()
