from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------
# Localização do JSON (robusto contra CWD diferente)
# ---------------------------------------------------------------------
CST_PATH = Path(__file__).resolve().parent / "cestas.json"


# ---------------------------------------------------------------------
# Cache em memória (carrega 1 vez)
# ---------------------------------------------------------------------
_BASKETS_RAW: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------
# Tags do seu enum (subset mínimo + fallback)
# (se quiser, você pode expandir conforme necessário)
# ---------------------------------------------------------------------
MACRO_TO_TAG = {
    "DOR_FEBRE_INFLAMACAO": "dor_generica",
    "RESPIRATORIO_GRIPE": "gripe_febre",
    "ALERGIAS": "alergia",
    "GASTROINTESTINAL": "gastro_digestivo",
    "PELE_DERMATO": "hidratacao_pele",
    "FERIDAS_CURATIVOS": "primeiros_socorros",
    "OLHOS_OUVIDOS_NARIZ": "nariz_sinus",
    "BOCA_GARGANTA_ODONTO": "higiene_oral",
    "SAUDE_INTIMA_URINARIO": "higiene_intima",
    "SAUDE_FEMININA_MENSTRUACAO": "saude_feminina",
    "PEDIATRIA": "criancas_bebe",
    "CRONICOS_CARDIOMETABOLICOS": "pressao_arterial_suporte",
    "ENDOCRINO_METABOLICO_SUPLEMENTOS": "vitaminas_minerais",
    "NEURO_PSIQUIATRIA_SONO": "sono_relaxamento_suporte",
    "HIGIENE_CUIDADOS_PESSOAIS_HPPC": "higiene_pessoal",
    "OUTRO": "outros",
}

# Heurística por palavra-chave para tag "mais específica" quando dá
TAG_KEYWORDS = [
    ("protetor solar", "protetor_solar"),
    ("pos-sol", "pos_sol"),
    ("pós-sol", "pos_sol"),
    ("repelente", "repelente"),
    ("curativo", "curativos"),
    ("gaze", "curativos"),
    ("micropore", "curativos"),
    ("antisséptico", "antisseptico_topico"),
    ("antisseptico", "antisseptico_topico"),
    ("soro", "soro_fisiologico_suporte"),
    ("solução nasal", "nariz_sinus"),
    ("spray nasal", "nariz_sinus"),
    ("pastilha", "garganta_tosse"),
    ("garganta", "garganta_tosse"),
    ("antiácido", "azia_refluxo"),
    ("antiacido", "azia_refluxo"),
    ("diarreia", "diarreia"),
    ("probiótico", "gastro_digestivo"),
    ("probiotico", "gastro_digestivo"),
    ("hidratante", "hidratacao_pele"),
    ("protetor labial", "protetor_labial"),
    ("sabonete íntimo", "higiene_intima"),
    ("sabonete intimo", "higiene_intima"),
    ("preservativo", "preservativos"),
    ("lubrificante", "lubrificantes"),
]


def _load_raw() -> Dict[str, Any]:
    global _BASKETS_RAW
    if _BASKETS_RAW is not None:
        return _BASKETS_RAW

    if not CST_PATH.exists():
        raise FileNotFoundError(f"cestas.json não encontrado em: {CST_PATH}")

    with CST_PATH.open("r", encoding="utf-8") as f:
        _BASKETS_RAW = json.load(f)

    # validação mínima de estrutura
    if "fallback_macro_default" not in _BASKETS_RAW:
        raise ValueError("cestas.json: faltando chave 'fallback_macro_default'")
    if "cestas_por_macro_micro" not in _BASKETS_RAW:
        raise ValueError("cestas.json: faltando chave 'cestas_por_macro_micro'")

    return _BASKETS_RAW


def reload_baskets() -> None:
    """Útil em dev/hot reload."""
    global _BASKETS_RAW
    _BASKETS_RAW = None


def _infer_tag(sugestao: str, macro: str) -> str:
    s = (sugestao or "").strip().lower()
    for kw, tag in TAG_KEYWORDS:
        if kw in s:
            return tag
    return MACRO_TO_TAG.get(macro, "outros")


def _ensure_item_shape(item: Dict[str, Any], macro: str) -> Dict[str, Any]:
    """
    Seu JSON hoje não tem 'tag'. Aqui a gente completa.
    """
    sugestao = item.get("sugestao")
    explicacao = item.get("explicacao") or ""

    tag = item.get("tag")
    if not tag:
        tag = _infer_tag(str(sugestao or ""), macro)

    return {
        "sugestao": sugestao,
        "explicacao": explicacao,
        "tag": tag,
    }


def get_basket_items(
    macro: str,
    micro: Optional[str] = None,
    *,
    max_items: int = 3
) -> List[Dict[str, Any]]:
    """
    Regra:
      - Se micro existir e houver cesta macro+micro -> usa ela
      - Senão -> fallback_macro_default[macro]
      - Senão -> []
    Retorna itens já com {sugestao, explicacao, tag}
    """
    raw = _load_raw()

    # 1) tenta macro+micro
    if micro:
        mm = raw.get("cestas_por_macro_micro", {}).get(macro, {})
        items = mm.get(micro)
        if isinstance(items, list) and items:
            shaped = [_ensure_item_shape(x, macro) for x in items]
            return shaped[:max_items]

    # 2) fallback por macro
    fb = raw.get("fallback_macro_default", {})
    items = fb.get(macro)
    if isinstance(items, list) and items:
        shaped = [_ensure_item_shape(x, macro) for x in items]
        return shaped[:max_items]

    return []


def resolve_basket_from_classification(
    classification: Dict[str, Any],
    *,
    max_items: int = 3
) -> List[Dict[str, Any]]:
    """
    Espera algo como:
      {"macros_top2":[...], "micro_categoria": "...|null", ...}
    Estratégia:
      - tenta macro1+micro, depois macro1 fallback
      - se vazio, tenta macro2+micro, depois macro2 fallback
      - se vazio, tenta OUTRO fallback
    """
    macros = classification.get("macros_top2") or []
    micro = classification.get("micro_categoria")

    # macro 1
    if len(macros) >= 1:
        items = get_basket_items(macros[0], micro, max_items=max_items)
        if items:
            return items

    # fallback macro 1 sem micro
    if len(macros) >= 1:
        items = get_basket_items(macros[0], None, max_items=max_items)
        if items:
            return items

    # macro 2
    if len(macros) >= 2:
        items = get_basket_items(macros[1], micro, max_items=max_items)
        if items:
            return items

    # fallback macro 2 sem micro
    if len(macros) >= 2:
        items = get_basket_items(macros[1], None, max_items=max_items)
        if items:
            return items

    # OUTRO
    items = get_basket_items("OUTRO", None, max_items=max_items)
    return items
