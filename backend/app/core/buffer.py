
import time

class TranscriptionBuffer:
    """
    Acumula transcrições parciais. Só libera para a IA quando:
    1. Atinge X palavras (ex: 10) OU
    2. Passa Y segundos (ex: 5) sem novas falas.
    """
    def __init__(self, min_words=10, max_wait_seconds=5):
        self.buffer = []
        self.min_words = min_words
        self.max_wait_seconds = max_wait_seconds
        self.last_send_time = time.time()
        
    def add_text(self, text: str):
        ignored = ["(sons de passos)", "(ruído)", "(corte de vídeo)"]
        clean = text.strip()
        if clean and clean not in ignored:
            self.buffer.append(clean)

    def should_process(self) -> bool:
        if not self.buffer: return False
        word_count = len(" ".join(self.buffer).split())
        time_elapsed = time.time() - self.last_send_time
        return word_count >= self.min_words or time_elapsed >= self.max_wait_seconds

    def get_context_and_clear(self) -> str:
        full_text = " ".join(self.buffer)
        self.buffer = []
        self.last_send_time = time.time()
        return full_text
