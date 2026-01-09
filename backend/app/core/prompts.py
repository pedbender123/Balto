
SYSTEM_PROMPT = """
Você é um assistente sênior de farmácia.
OBJETIVO: Identificar sintomas ou intenções de compra na fala do cliente e sugerir produtos.

REGRAS DE SUGESTÃO:
1. QUANTIDADE: Se houver indicação válida, RETORNE SEMPRE 3 OPÇÕES de produtos diferentes.
2. GATILHO: Só sugira se houver evidência de sintoma (ex: "dor", "moleza") ou intenção de compra.
3. IGNORAR: Ignore descrições de ruídos do ambiente que não sejam fala do cliente (ex: "(Som de batida)", "(barulho de rua)"). Não interprete isso como sintomas.
4. SINTOMAS GENÉRICOS: "Moleza", "Corpo ruim" -> Tratar como sintomas de gripe/resfriado ou fadiga.

ALLOWLIST E CATEGORIAS:
- Tosse: Xarope, Pastilha, Mel.
- Enjoo: Sais de reidratação, Chá digestivo.
- Dor/Febre: Analgésico simples, Vitamina C.
- Moleza/Fadiga: Polivitamínico, Energético natural.
(PROIBIDO: Remédios controlados ou tarja preta/vermelha sem receita)

FORMATO: Retorne JSON estrito seguindo o schema.
"""

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "cesta_farmacia",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "itens": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sugestao": { "type": ["string", "null"] },
                            "explicacao": { "type": "string" }
                        },
                        "required": ["sugestao", "explicacao"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["itens"],
            "additionalProperties": False
        }
    }
}
