# app/core/cestas_lookup.py
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LOOKUP_PATH = Path(__file__).resolve().parent / "cestas_produtos_sintomas_doencas.json"
_CACHE: Optional[Dict[str, Any]] = None

def _norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s

def _load_lookup() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not LOOKUP_PATH.exists():
        raise FileNotFoundError(f"JSON não encontrado em: {LOOKUP_PATH}")
    with LOOKUP_PATH.open("r", encoding="utf-8") as f:
        _CACHE = json.load(f)
    return _CACHE

_RE_MED  = re.compile(r"(?:^|;)\s*MED\s*:\s*([^;|]+)", re.IGNORECASE)
_RE_SINT = re.compile(r"(?:^|;)\s*SINT\s*:\s*([^;|]+)", re.IGNORECASE)
_RE_DOEN = re.compile(r"(?:^|;)\s*DOENCA\s*:\s*([^;|]+)", re.IGNORECASE)

def parse_prompt1(normalizado_out: str) -> Tuple[str, str, str]:
    s = (normalizado_out or "").strip()

    med = ""
    m = _RE_MED.search(s)
    if m: med = _norm_text(m.group(1))

    sint = ""
    m = _RE_SINT.search(s)
    if m: sint = _norm_text(m.group(1))

    doenca = ""
    m = _RE_DOEN.search(s)
    if m: doenca = _norm_text(m.group(1))

    return med, sint, doenca

def _key(*parts: str) -> str:
    return "_".join([p for p in parts if p])

def lookup_cesta(med: str, sint: str, doenca: str) -> Optional[List[Dict[str, str]]]:
    """
    Ordem:
      1) med_sint_doenca
      2) med_sint_default
      3) med_default
    Retorna lista (4 itens no JSON) ou None
    """
    data = _load_lookup()

    med = _norm_text(med)
    sint = _norm_text(sint)
    doenca = _norm_text(doenca)

    if not med:
        return None

    candidates = []
    if sint and doenca:
        candidates.append(_key(med, sint, doenca))
    if sint:
        candidates.append(_key(med, sint, "default"))
    candidates.append(_key(med, "default"))

    for k in candidates:
        items = data.get(k)
        if isinstance(items, list) and items:
            out = []
            for it in items:
                produto = (it.get("produto") or "").strip()
                explic = (it.get("explicacao") or "").strip()
                if produto:
                    out.append({"produto": produto, "explicacao": explic})
            if out:
                return out
    return None