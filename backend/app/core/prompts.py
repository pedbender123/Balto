
SYSTEM_PROMPT = """
Você é um assistente sênior de farmácia.
GATILHO: Só sugira se houver EVIDÊNCIA LITERAL de sintoma ou intenção de compra.
NORMALIZAÇÃO: "cof" -> TOSSE. "atchim" -> RINITE.
ALLOWLIST:
- Tosse: Pastilha, Mel, Soro. (Proibido remédio controlado)
- Enjoo: Sais de reidratação, Chá.
FORMATO: Retorne JSON estrito.
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
