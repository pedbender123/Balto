import os
import requests
import openpyxl
import base64
import json
import time
import wave

# Configurações
# Default to Localhost for local testing ease, per user request. 
# Can be overridden by BALTO_SERVER_URL env var.
SERVER_URL = os.environ.get("BALTO_SERVER_URL", "http://localhost:8765") 
print(f"Using Server URL: {SERVER_URL}")

INPUT_DIR = "testes/1_input"
OUTPUT_DIR = "testes/planilhas"
SEGMENTS_TEMP = "testes/2_cortados"

# Arquivos de Saída
FILE_ORIGINAIS = os.path.join(OUTPUT_DIR, "Relatorio_Originais.xlsx")
FILE_SEGMENTOS = os.path.join(OUTPUT_DIR, "Relatorio_Segmentos.xlsx")

HEADERS_ORIGINAIS = [
    'Nome do Arquivo',
    'Transcrição Completa (ElevenLabs)'
]

HEADERS_SEGMENTOS = [
    'Arquivo Original', 
    'Nome do Segmento', 
    'Duração (s)', 
    'Transcrição ElevenLabs (Segmento)', 
    'Transcrição AssemblyAI (Segmento)',
    'Transcrição Deepgram (Segmento)',
    'Transcrição Gladia (Segmento)', 
    'Qualidade', 
    'Acurácia'
]

# ... unchanged ...

            print(f"    -> Seg {i}: Transcrevendo (Eleven, Assembly, Deepgram, Gladia)...")
            text_eleven = transcribe_file(seg_path, "elevenlabs")
            text_assembly = transcribe_file(seg_path, "assemblyai")
            text_deepgram = transcribe_file(seg_path, "deepgram")
            text_gladia = transcribe_file(seg_path, "gladia")
            
            row = [
                filename,
                seg_name,
                f"{duration:.2f}",
                text_eleven,
                text_assembly,
                text_deepgram,
                text_gladia,
                "", # Qualidade
                ""  # Acuracia
            ]
            ws_seg.append(row)
        
        # Salvar planilha de segmentos a cada arquivo processado para não perder progresso
        wb_seg.save(FILE_SEGMENTOS)

    print(f"\nConcluído!")
    print(f"Relatório Originais: {FILE_ORIGINAIS}")
    print(f"Relatório Segmentos: {FILE_SEGMENTOS}")

if __name__ == "__main__":
    main()
