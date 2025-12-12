import numpy as np
import sqlite3
import os
from app import db

# Tenta importar Resemblyzer. Se falhar (dev environment), usa Mock.
try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    # Carrega o encoder na memória (pesado, fazer uma vez só)
    encoder = VoiceEncoder()
    HAS_SPEAKER_ID = True
    print("[SpeakerID] Modelo carregado com sucesso.")
except ImportError:
    HAS_SPEAKER_ID = False
    print("[SpeakerID] Resemblyzer não encontrado. Modo SpeakerID desativado.")
except Exception as e:
    HAS_SPEAKER_ID = False
    print(f"[SpeakerID] Erro ao carregar modelo: {e}")

def get_embedding(audio_bytes: bytes):
    """Gera vetor de características da voz."""
    if not HAS_SPEAKER_ID: return None
    
    # Resemblyzer espera array numpy float32 normalizado
    wav = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
    # Normalização simples se necessário, mas preprocess_wav geralmente lida com arquivos
    # Para buffer raw, o encoder lida bem se normalizado entre -1 e 1
    wav = wav / 32768.0 
    
    embedding = encoder.embed_utterance(wav)
    return embedding

def identificar_funcionario(audio_bytes: bytes, balcao_id: str):
    """
    Compara o áudio atual com os embeddings dos funcionários cadastrados.
    Retorna dict {id, nome} ou None.
    """
    if not HAS_SPEAKER_ID: return None
    
    # 1. Gera embedding do áudio atual
    current_emb = get_embedding(audio_bytes)
    if current_emb is None: return None
    
    # 2. Busca funcionários do usuário dono deste balcão
    # Precisamos achar o user_id dono do balcao_id primeiro
    # (Otimização: cachear isso)
    funcionarios = db.listar_funcionarios_por_balcao(balcao_id)
    
    melhor_match = None
    maior_similaridade = 0.0
    threshold = 0.75 # Limiar de certeza
    
    for func in funcionarios:
        nome = func['nome']
        emb_blob = func['embedding']
        if not emb_blob: continue
        
        # Converte BLOB de volta para numpy
        known_emb = np.frombuffer(emb_blob, dtype=np.float32)
        
        # Distância Cosseno (Produto escalar de vetores normalizados)
        # O Resemblyzer já normaliza L2 os embeddings
        similarity = np.inner(current_emb, known_emb)
        
        if similarity > maior_similaridade:
            maior_similaridade = similarity
            melhor_match = func
            
    if melhor_match and maior_similaridade > threshold:
        return {"id": melhor_match['id'], "nome": melhor_match['nome']}
        
    return None

def enroll_funcionario(audio_bytes: bytes, nome: str, user_id: str):
    """Cadastra um novo funcionário."""
    emb = get_embedding(audio_bytes)
    if emb is not None:
        # Salva como bytes (BLOB)
        emb_blob = emb.tobytes()
        db.adicionar_funcionario(user_id, nome, emb_blob)
        return True
    return False