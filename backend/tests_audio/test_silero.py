import torch
import sys

try:
    print("Tentando carregar Silero VAD via torch.hub...")
    model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad',
                                  model='silero_vad',
                                  force_reload=False,
                                  trust_repo=True)
    (get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils
    print("Sucesso! Silero VAD carregado.")
except Exception as e:
    print(f"Erro ao carregar Silero: {e}")
    sys.exit(1)
