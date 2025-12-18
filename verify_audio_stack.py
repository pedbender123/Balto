import sys
import os
import numpy as np

# Adiciona o diretório atual ao path para importar os módulos
sys.path.append(os.getcwd())

try:
    from backend.app.audio_processor import AudioCleaner
    from backend.app.vad import VAD
    print("[TEST] Imports OK")
except Exception as e:
    print(f"[TEST] Erro de Import: {e}")
    sys.exit(1)

def generate_test_signal(duration_sec, sample_rate=16000, type='silence'):
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    if type == 'silence':
        # Ruído muito baixo
        return (np.random.normal(0, 10, t.shape)).astype(np.int16)
    elif type == 'speech':
        # Senoide forte simulando voz
        return (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)
    elif type == 'noise':
        # Ruído constante (zumbido)
        return (np.random.normal(0, 500, t.shape)).astype(np.int16)

def test_pipeline():
    print("[TEST] Iniciando Teste de Pipeline...")
    
    cleaner = AudioCleaner()
    vad = VAD()
    
    # 1. Simular 2 segundos de ruído de fundo (para calibrar o VAD/Cleaner inicialmente)
    print("\n--- Fase 1: Ruído de Fundo (Calibração) ---")
    noise = generate_test_signal(2.0, type='noise')
    chunk_size = 480 # 30ms
    
    noise_bytes = noise.tobytes()
    for i in range(0, len(noise_bytes), chunk_size * 2):
        chunk = noise_bytes[i:i + chunk_size * 2]
        if len(chunk) < chunk_size * 2: break
        
        cleaned = cleaner.process(chunk)
        speech = vad.process(cleaned)
        # Esperamos que NÃO detecte fala aqui, ou se adaptar rápido

    # 2. Simular 1 segundo de fala
    print("\n--- Fase 2: Fala Simulada (Esperado Trigger) ---")
    speech_sig = generate_test_signal(1.0, type='speech')
    speech_bytes = speech_sig.tobytes()
    
    detected = False
    
    for i in range(0, len(speech_bytes), chunk_size * 2):
        chunk = speech_bytes[i:i + chunk_size * 2]
        if len(chunk) < chunk_size * 2: break
        
        cleaned = cleaner.process(chunk)
        result = vad.process(cleaned)
        
        if vad.triggered:
            detected = True
            
    print(f"\n[TEST] Fala Detectada? {'SIM' if detected else 'NAO'}")
    
    # 3. Simular silêncio pós-fala para fechar segmento
    print("\n--- Fase 3: Silêncio (Esperado Segmento) ---")
    silence = generate_test_signal(1.0, type='silence')
    silence_bytes = silence.tobytes()
    
    segment_captured = False
    
    for i in range(0, len(silence_bytes), chunk_size * 2):
        chunk = silence_bytes[i:i + chunk_size * 2]
        cleaned = cleaner.process(chunk)
        result = vad.process(cleaned)
        
        if result:
            print(f"[TEST] Segmento Capturado! Tamanho: {len(result)} bytes")
            segment_captured = True
            break
            
    if segment_captured:
        print("[TEST] SUCESSO: Pipeline completo validado.")
    else:
        print("[TEST] FALHA: Segmento não foi finalizado corretamente.")

if __name__ == "__main__":
    test_pipeline()
