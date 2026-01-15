# backend/app/tools/tune_vad.py
from __future__ import annotations

import argparse
import os
import sys
from glob import glob
from dataclasses import dataclass
from typing import List, Tuple

from app import vad
from app.core import audio_utils


@dataclass
class FileReport:
    path: str
    total_sec: float
    n_segments: int
    speech_sec: float
    avg_seg_sec: float
    p50_seg_sec: float
    short_seg_pct: float   # % segmentos < 1.0s


def _pct(x: float) -> float:
    return 100.0 * x


def load_as_pcm16(path: str) -> bytes | None:
    """
    Retorna PCM16 mono 16k (bytes) a partir de:
      - .webm -> decode_webm_to_pcm16le
      - .wav  -> tenta ler PCM direto (sem resample)
    """
    ext = os.path.splitext(path)[1].lower()

    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as e:
        print(f"[SKIP] cannot read file: {path} ({e})")
        return None

    if ext == ".webm":
        pcm = audio_utils.decode_webm_to_pcm16le(raw)
        return pcm if pcm else None

    if ext == ".wav":
        # Se seus WAVs não forem PCM16 mono 16k, melhor converter antes.
        try:
            import wave
            with wave.open(path, "rb") as wf:
                frames = wf.readframes(wf.getnframes())
            return frames if frames else None
        except Exception as e:
            print(f"[SKIP] cannot read wav: {path} ({e})")
            return None

    print(f"[SKIP] unsupported extension: {path}")
    return None


def p50(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 == 1 else (s[mid - 1] + s[mid]) / 2.0


def run_vad_on_pcm(pcm: bytes, chunk_size: int) -> Tuple[List[bytes], float]:
    """
    Roda seu VAD atual em cima do PCM16.
    Retorna (segments, total_sec)
    """
    v = vad.VAD()  # usa seus defaults atuais
    segments: List[bytes] = []

    total_sec = len(pcm) / 32000.0  # 16kHz * 2 bytes
    if not pcm:
        return segments, 0.0

    # alimenta em chunks constantes (simula o streaming)
    for i in range(0, len(pcm), chunk_size):
        chunk = pcm[i : i + chunk_size]
        seg = v.process(chunk)
        if seg:
            segments.append(seg)

    # flush "na marra": manda alguns frames de silêncio pra forçar fechar segmento
    # (se estiver triggered e faltou silêncio no fim do arquivo)
    silence = b"\x00" * max(chunk_size, 1920)
    for _ in range(50):  # ~3s dependendo do chunk
        seg = v.process(silence)
        if seg:
            segments.append(seg)
            break

    return segments, total_sec


def report_for_file(path: str, chunk_size: int) -> FileReport | None:
    pcm = load_as_pcm16(path)
    if pcm is None:
        return None

    segments, total_sec = run_vad_on_pcm(pcm, chunk_size)

    seg_secs = [len(s) / 32000.0 for s in segments]
    speech_sec = sum(seg_secs)
    n = len(seg_secs)
    avg_seg = (speech_sec / n) if n else 0.0
    med = p50(seg_secs)
    short_pct = (_pct(sum(1 for x in seg_secs if x < 1.0) / n) if n else 0.0)

    return FileReport(
        path=path,
        total_sec=total_sec,
        n_segments=n,
        speech_sec=speech_sec,
        avg_seg_sec=avg_seg,
        p50_seg_sec=med,
        short_seg_pct=short_pct,
    )


def score_cutting(r: FileReport) -> float:
    """
    Heurística de "cortou demais":
      - muitos segmentos curtos
      - mediana baixa
      - muitos segmentos por minuto
    """
    if r.total_sec <= 0:
        return 1e9
    seg_per_min = r.n_segments / max(1e-9, (r.total_sec / 60.0))
    return (r.short_seg_pct * 2.0) + (max(0.0, 2.0 - r.p50_seg_sec) * 50.0) + (seg_per_min * 3.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Pasta base com arquivos")
    ap.add_argument("--glob", default="**/*.webm", help='Ex: "*.webm" ou "**/*.webm"')
    ap.add_argument("--top", type=int, default=10, help="Top N piores arquivos (mais cortados)")
    ap.add_argument("--chunk", type=int, default=1920, help="Chunk PCM em bytes (1920 ~ 60ms)")
    args = ap.parse_args()

    base = args.input
    pattern = os.path.join(base, args.glob)
    files = sorted(glob(pattern, recursive=True))

    if not files:
        print("Nenhum arquivo encontrado.")
        sys.exit(1)

    reports: List[FileReport] = []
    for idx, path in enumerate(files, 1):
        print(f"[{idx}/{len(files)}] {path}")
        r = report_for_file(path, args.chunk)
        if r:
            reports.append(r)

    if not reports:
        print("Nenhum arquivo decodificou para PCM16. (ffmpeg/decoder pode estar falhando)")
        sys.exit(2)

    # Ordena pelos piores (mais "corte")
    reports.sort(key=score_cutting, reverse=True)

    print("\n=== SUMMARY (top worst cutting) ===")
    for r in reports[: args.top]:
        seg_per_min = r.n_segments / max(1e-9, (r.total_sec / 60.0))
        speech_ratio = (_pct(r.speech_sec / r.total_sec) if r.total_sec else 0.0)
        print(
            f"\nFILE: {r.path}\n"
            f"  total_sec={r.total_sec:.1f}  speech_sec={r.speech_sec:.1f}  speech_ratio={speech_ratio:.1f}%\n"
            f"  segments={r.n_segments}  seg/min={seg_per_min:.1f}\n"
            f"  avg_seg={r.avg_seg_sec:.2f}s  p50_seg={r.p50_seg_sec:.2f}s  short(<1s)={r.short_seg_pct:.1f}%"
        )

    # Diagnóstico geral (bem direto)
    all_seg_secs = []
    for r in reports:
        # aproximação: não temos os segs aqui, mas já dá pra inferir pelo p50/short_pct e n_segments
        pass

    print("\n=== QUICK DIAGNOSIS (heuristic) ===")
    worst = reports[0]
    if worst.short_seg_pct > 50 or worst.p50_seg_sec < 1.2:
        print("- Está cortando demais (muitos segmentos < 1s e/ou mediana baixa).")
        print("  Próximos knobs MAIS prováveis no seu vad.py:")
        print("  1) aumentar silence_frames_needed (segura mais antes de fechar)")
        print("  2) aumentar pre_roll_buffer (não perder início da fala)")
        print("  3) reduzir threshold_multiplier e/ou min_energy_threshold (abrir gate mais cedo)")
        print("  4) reduzir vad_aggressiveness (3 -> 2) se estiver perdendo voz fraca")
    else:
        print("- Não parece corte extremo na pior amostra, mas valide com mais arquivos.")

    print("\nOK")


if __name__ == "__main__":
    main()
