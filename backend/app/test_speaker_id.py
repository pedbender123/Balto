# app/test_speaker_id.py
#
# Teste offline do módulo de identificação de voz:
# 1) Usa os perfis já cadastrados em speaker_profiles
# 2) Lê WAVs de teste em audio_dumps/testes_voiceid
# 3) Testa:
#    - identificação "batch" (áudio inteiro)
#    - identificação por segmentos usando diarização mock (DIARIZACAO_TESTE)
#    - identificação em "streaming" (chunks pequenos)

import os
import wave
from glob import glob

import numpy as np  # <--- IMPORTANTE

from app import speaker_id, db


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.join(BASE_DIR, "audio_dumps", "testes_voiceid")

# Diarização mock (vinda da ElevenLabs + tua montagem)
DIARIZACAO_TESTE = {
    "bloco_atendimento_camila_zilli.wav": [
        { "speaker": "A", "text": "Como é que foi essa história da Holly, aquela que chuga lá?", "confidence": 0.6587478, "start_ms": 903, "end_ms": 4083, },
        { "speaker": "B", "text": "Que?", "confidence": 0.806, "start_ms": 4883, "end_ms": 5183, },
        { "speaker": "A", "text": "Holly não, a outra que você falou que tava atirando em todo mundo, que é a Nancy.", "confidence": 0.65432453, "start_ms": 5443, "end_ms": 11263, },
        { "speaker": "B", "text": "Ah, sim, a Nancy. É ela mesmo. Tava atirando em vários militares lá no Mundo Invertido.", "confidence": 0.7527007, "start_ms": 11443, "end_ms": 17683, },
        { "speaker": "A", "text": "Militares? Caramba.", "confidence": 0.8, "start_ms": 18263, "end_ms": 20783, },
        { "speaker": "B", "text": "Quando.", "confidence": 0.43408203, "start_ms": 21403, "end_ms": 22343, },
        { "speaker": "A", "text": "Que vai lançar mesmo?", "confidence": 0.7589512, "start_ms": 22343, "end_ms": 23183, },
        { "speaker": "B", "text": "Dia 26.", "confidence": 0.92690235, "start_ms": 23643, "end_ms": 24563, },
        { "speaker": "A", "text": "Ai, ótimo.", "confidence": 0.639, "start_ms": 25003, "end_ms": 25603, }
    ],
    "bloco_atendimento_aleatorio_cortado.wav": [
        { "speaker": "A", "text": "Para mais informações ou para ser voluntário, por favor visite LibriVox.org. Mateus e Mateusa. Personagens. Narração. Gravado por Leni.", "confidence": 0.75271016, "start_ms": 8, "end_ms": 10968, },
        { "speaker": "B", "text": "Mateus. Gravado por Jefferson Azevedo.", "confidence": 0.89516747, "start_ms": 11448, "end_ms": 14168, },
        { "speaker": "C", "text": "Mateusa. Gravado por Cristina Luiz.", "confidence": 0.89302385, "start_ms": 14888, "end_ms": 18568, },
        { "speaker": "D", "text": "Catarina. Gravado por Sofia Seabra.", "confidence": 0.86505467, "start_ms": 19628, "end_ms": 22668, },
        { "speaker": "D", "text": "Pedra. Gravado por Silvio Wolf.", "confidence": 0.7886263, "start_ms": 23528, "end_ms": 25928, },
        { "speaker": "D", "text": "Silvestre, gravado por Sofia Seabra.", "confidence": 0.7324879, "start_ms": 27059, "end_ms": 30619, }
    ],
    "bloco_atendimento_aleatorio_camila_zilli_16k.wav": [
        { "speaker": "A", "text": "Informações ou para ser voluntário, por favor visite debrevox.org.", "confidence": 0.73056185, "start_ms": 8, "end_ms": 4988 },
        { "speaker": "B", "text": "Como é que foi essa história da... a Holly, aquela queixuda lá?", "confidence": 0.6795207, "start_ms": 6188, "end_ms": 10028 },
        { "speaker": "A", "text": "Que?", "confidence": 0.767, "start_ms": 10828, "end_ms": 11168 },
        { "speaker": "B", "text": "Holly, não. A... a outra que você falou que tava atirando em todo mundo, que é a Nance Queixuda.", "confidence": 0.64273494, "start_ms": 11428, "end_ms": 17087 },
        { "speaker": "A", "text": "Ah, sim, a Nance. É. É ela mesmo. Tava atirando em vários militares lá no mundo invertido.", "confidence": 0.79613143, "start_ms": 17088, "end_ms": 23668 },
        { "speaker": "B", "text": "Militares? Caramba.", "confidence": 0.7775, "start_ms": 24248, "end_ms": 26788 },
        { "speaker": "A", "text": "É.", "confidence": 0.638, "start_ms": 27388, "end_ms": 27728 },
        { "speaker": "B", "text": "Quando que vai lançar mesmo?", "confidence": 0.7664223, "start_ms": 28148, "end_ms": 29168 },
        { "speaker": "A", "text": "Dia 26.", "confidence": 0.44773096, "start_ms": 29658, "end_ms": 30598 },
        { "speaker": "B", "text": "Ai, ótimo, legal.", "confidence": 0.59166664, "start_ms": 31018, "end_ms": 31858 }
    ],
}


def recortar_segmento(audio_pcm16: bytes, start_ms: float, end_ms: float, sr: int = 16000) -> bytes:
    """
    Recorta um trecho [start_ms, end_ms] de um áudio PCM16 (mono) em bytes.
    Faz clipping para não estourar o tamanho do array.
    """
    audio_np = np.frombuffer(audio_pcm16, dtype=np.int16)
    n_samples = len(audio_np)

    start_sample = int((start_ms / 1000.0) * sr)
    end_sample   = int((end_ms   / 1000.0) * sr)

    start_sample = max(0, min(start_sample, n_samples))
    end_sample   = max(0, min(end_sample,   n_samples))

    if end_sample <= start_sample:
        return b""

    trecho_np = audio_np[start_sample:end_sample]
    return trecho_np.astype(np.int16).tobytes()


def calcular_scores_por_balconista(emb_atendimento, perfis):
    """
    Retorna lista [(balconista_id, score_coseno), ...] ordenada por score desc.
    """
    scores = []
    for balconista_id, emb_ref in perfis.items():
        sim = speaker_id.similaridade_coseno(emb_atendimento, emb_ref)
        scores.append((balconista_id, sim))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def ler_wav_pcm16(path: str) -> bytes:
    with wave.open(path, "rb") as wf:
        print(f"[TEST_VOICEID] Lendo arquivo: {path}")
        print(
            f"  canais={wf.getnchannels()}, "
            f"samplewidth={wf.getsampwidth()}, "
            f"framerate={wf.getframerate()}"
        )
        assert wf.getnchannels() == 1, "WAV deve ser mono"
        assert wf.getsampwidth() == 2, "WAV deve ser 16-bit"
        assert wf.getframerate() == speaker_id.SAMPLE_RATE, f"WAV deve ser {speaker_id.SAMPLE_RATE} Hz"
        frames = wf.readframes(wf.getnframes())
    return frames


def teste_batch():
    """
    Teste antigo: pega o áudio inteiro, faz uma diarização fake (um speaker só)
    e roda identificar_balconista() + ranking de scores.
    """
    print("\n=== [1] Teste batch: identificar_balconista() em áudios inteiros ===")

    wav_files = sorted(glob(os.path.join(TEST_DIR, "*.wav")))
    if not wav_files:
        print(f"[TEST_VOICEID] Nenhum WAV encontrado em: {TEST_DIR}")
        return

    # Garante DB inicializado e carrega perfis
    db.inicializar_db()
    perfis = speaker_id.carregar_perfis_balconistas()
    print(f"[TEST_VOICEID] Perfis encontrados no banco: {list(perfis.keys())}\n")

    for wav_path in wav_files:
        audio = ler_wav_pcm16(wav_path)
        duracao_seg = len(audio) / (2 * speaker_id.SAMPLE_RATE)

        # Diarização fake: um único speaker ocupando o áudio todo
        diarization_fake = [
            {"speaker": "spk_0", "start": 0.0, "end": duracao_seg}
        ]

        balconista_pred, score_pred = speaker_id.identificar_balconista(
            audio_pcm16=audio,
            diarization=diarization_fake,
            threshold=0.0,  # sem "não sei" aqui, queremos ver score bruto
        )

        emb_atendimento = speaker_id.extrair_embedding(audio, sample_rate=speaker_id.SAMPLE_RATE)
        scores = calcular_scores_por_balconista(emb_atendimento, perfis)

        print(f"- Arquivo: {os.path.basename(wav_path)}")
        print(f"  duração: {duracao_seg:.2f}s")
        print(f"  pred_top1: {balconista_pred} | score_pred={score_pred:.3f}")
        print("  scores por balconista:")
        for balconista_id, sim in scores:
            print(f"    - {balconista_id}: {sim:.3f}")
        print()


def teste_segmentos_mock():
    """
    NOVO: usa DIARIZACAO_TESTE para:
      - recortar cada frase/segmento
      - gerar embedding por segmento
      - mostrar ranking de scores por balconista para cada trecho
    """
    print("\n=== [2] Teste por segmentos com diarização mock ===")

    wav_files = sorted(glob(os.path.join(TEST_DIR, "*.wav")))
    if not wav_files:
        print(f"[TEST_VOICEID] Nenhum WAV encontrado em: {TEST_DIR}")
        return

    db.inicializar_db()
    perfis = speaker_id.carregar_perfis_balconistas()
    print(f"[TEST_VOICEID] Perfis encontrados no banco: {list(perfis.keys())}\n")

    for wav_path in wav_files:
        fname = os.path.basename(wav_path)
        audio = ler_wav_pcm16(wav_path)

        if fname not in DIARIZACAO_TESTE:
            print(f"\n>> {fname}: sem diarização mock, pulando teste por segmentos.")
            continue

        print(f"\n>> Arquivo: {fname} — testando segmentos diarizados")
        segmentos = DIARIZACAO_TESTE[fname]

        for idx, seg in enumerate(segmentos, start=1):
            trecho = recortar_segmento(
                audio,
                seg["start_ms"],
                seg["end_ms"],
                sr=speaker_id.SAMPLE_RATE,
            )
            dur_seg = len(trecho) / (2 * speaker_id.SAMPLE_RATE)

            if dur_seg < 0.5:
                print(f"  - Segmento {idx}: muito curto ({dur_seg:.2f}s), pulando.")
                continue

            emb = speaker_id.extrair_embedding(trecho, sample_rate=speaker_id.SAMPLE_RATE)
            if emb is None:
                print(f"  - Segmento {idx}: embedding None, pulando.")
                continue

            # Usa a regra de decisão com "NÃO SEI"
            pred_id, top_score, ranking = speaker_id.classificar_por_scores(
                emb,
                perfis,
                threshold=0.82,   # pode ajustar depois
                margin=0.05,      # gap mínimo entre top1 e top2
            )

            print(f"  - Segmento {idx}: speaker_label={seg['speaker']}, dur={dur_seg:.2f}s")
            print(f"    texto: {seg['text']}")
            print(f"    top_score={top_score:.3f}")

            if pred_id is None:
                print("    >>> DECISÃO: NÃO SEI")
            else:
                print(f"    >>> DECISÃO: {pred_id}")

            print("    ranking:")
            for balconista_id, sim in ranking:
                print(f"      - {balconista_id}: {sim:.3f}")
            print()


def teste_streaming():
    """
    Mesmo teste que você já tinha: simula chunks de 0.5s
    e deixa o StreamVoiceIdentifier tentar identificar com ~3s.
    """
    print("\n=== [3] Teste streaming: StreamVoiceIdentifier em chunks ===")

    wav_files = sorted(glob(os.path.join(TEST_DIR, "*.wav")))
    if not wav_files:
        print(f"[TEST_VOICEID] Nenhum WAV encontrado em: {TEST_DIR}")
        return

    db.inicializar_db()

    for wav_path in wav_files:
        audio = ler_wav_pcm16(wav_path)
        total_dur = len(audio) / (2 * speaker_id.SAMPLE_RATE)

        tracker = speaker_id.StreamVoiceIdentifier(
            enabled=True,
            threshold=0.0,      # deixa sempre aceitar alguém, só pra ver o score bruto
            min_duration=3.0,   # 3s de fala acumulada para testar rápido
        )

        chunk_samples = int(0.5 * speaker_id.SAMPLE_RATE)
        chunk_bytes = chunk_samples * 2

        print(f"\n>> Streaming de {os.path.basename(wav_path)} (dur={total_dur:.2f}s)")

        acumulado_seg = 0.0
        identificado = False

        for i in range(0, len(audio), chunk_bytes):
            seg = audio[i:i + chunk_bytes]
            acumulado_seg += 0.5

            balconista_pred, score = tracker.add_segment("TESTE", seg)
            if balconista_pred is not None:
                print(
                    f"  [OK] Identificado com {acumulado_seg:.1f}s de áudio: "
                    f"{balconista_pred} (score={score:.3f})"
                )
                identificado = True
                break

        if not identificado:
            print("  [!] Não conseguiu identificar com o áudio disponível.")


def main():
    print(f"[TEST_VOICEID] Pasta de testes: {TEST_DIR}")
    teste_batch()
    teste_segmentos_mock()
    teste_streaming()


if __name__ == "__main__":
    main()
