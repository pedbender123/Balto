import os
import requests
import openpyxl
import base64
import json
import time
import wave

# Configurações
SERVER_URL = "https://balto.pbpmdev.com" 
INPUT_DIR = "testes/1_input"
OUTPUT_DIR = "testes/planilhas"
SEGMENTS_TEMP = "testes/2_cortados"

HEADERS = [
    'Nome do arquivo original', 
    'Transcrição Elevenlabs do arquivo original', 
    'Nome do arquivo cortado', 
    'Quantidade de segundos do arquivo cortado', 
    'Transcrição Elevenlabs do arquivo cortado', 
    'Transcrição Soniox do arquivo cortado', 
    'Qualidade (se true então vai para Soniox)', 
    'Acurácia (quantos % acertou?)'
]

def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(SEGMENTS_TEMP, exist_ok=True)

def transcribe_file(filepath, provider):
    with open(filepath, 'rb') as f:
        # Check ext to decide MIME, though server handles basic read
        files = {
            'audio': (os.path.basename(filepath), f, 'audio/wav'),
            'provider': (None, provider)
        }
        res = requests.post(f"{SERVER_URL}/api/test/transcrever", files=files)
        if res.status_code == 200:
            return res.json().get("texto", "")
    return ""

def segment_file(filepath):
    with open(filepath, 'rb') as f:
        files = {'audio': (os.path.basename(filepath), f, 'audio/webm')}
        res = requests.post(f"{SERVER_URL}/api/test/segmentar", files=files)
        if res.status_code == 200:
            return res.json().get("segments", [])
    return []

def main():
    ensure_dirs()
    input_files = [f for f in os.listdir(INPUT_DIR) if not f.startswith('.')]
    
    # Limitar a 3 audios como pedido
    input_files = input_files[:3]
    
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    
    for filename in input_files:
        print(f"Processando: {filename}")
        original_path = os.path.join(INPUT_DIR, filename)
        
        # 1. Transcrever Original (ElevenLabs) - SKIPPED as per user request
        print(" -> Transcrevendo Original (SKIPPED)...")
        original_transcript = "" # transcribe_file(original_path, "elevenlabs")
        
        # 2. Segmentar
        print(" -> Segmentando...")
        segments = segment_file(original_path)
        print(f"    {len(segments)} segmentos.")
        
        for i, seg in enumerate(segments):
            # Salvar chunk temporariamente para enviar pra transcrição
            seg_name = f"{os.path.splitext(filename)[0]}_seg_{i:03d}.wav"
            seg_path = os.path.join(SEGMENTS_TEMP, seg_name)
            
            raw_bytes = base64.b64decode(seg["audio_base64"])
            
            # wrap in wav
            with wave.open(seg_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(raw_bytes)
                
            duration = seg["duration_sec"]
            
            # 3. Transcrever Segmento (Eleven + Assembly)
            print(f" -> Segmento {i}: Transcrevendo Dupla...")
            text_eleven = transcribe_file(seg_path, "elevenlabs")
            text_assembly = transcribe_file(seg_path, "assemblyai")
            
            # 4. Qualidade
            # Como a API teste não retorna SNR na rota /transcrever, vamos simular ou deixar em branco
            # A rota inteligente retorna 'snr', mas aqui estamos chamando transcrever direto.
            # Vamos deixar 'N/A' ou tentar deduzir se o usuário quiser. O user pediu estrutura.
            qualidade = "N/A"
            
            row = [
                filename,               # Original Name
                original_transcript,    # Original Texto
                seg_name,               # Segment Name
                f"{duration:.2f}",      # Seconds
                text_eleven,            # Transcrição Seg Eleven
                text_assembly,          # Transcrição Seg Soniox (Assembly)
                qualidade,              # Qualidade
                ""                      # Acurácia (Manual?)
            ]
            sheet.append(row)
            
    out_file = os.path.join(OUTPUT_DIR, "Relatorio_Teste_Final.xlsx")
    workbook.save(out_file)
    print(f"\nRelatório salvo em: {out_file}")

if __name__ == "__main__":
    main()
