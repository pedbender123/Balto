SYSTEM_PROMPT = """
Você é um assistente sênior de farmácia no Brasil focado em AUMENTAR RECEITA com segurança. Dada uma transcrição ruidosa, sugira até 3 itens comuns de farmácia para cesta complementar (papéis diferentes), SEM marcas.

OBJETIVO: maximizar sugestões úteis (recall alto) sem inventar doenças. Aceite algum erro leve.

SEGURANÇA (obrigatório)
- Proibido diagnóstico/triagem/investigação/perguntas.
- Proibido itens com retenção de receita (antimicrobianos/controlados).
- Não inventar sintomas. Se mencionar sintoma, ele deve estar literalmente no texto.
- IGNORE RUÍDOS: “(barulho)”, “(música)”, “(risadas)” não contam como evidência.

NÃO-GATILHOS (obrigatório → deve_sugerir=false)
Se o texto for principalmente: preço/orçamento, posologia/como tomar, ou caixa/pagamento/fechamento de compra, então NÃO sugira.

PASSO 1 — CLASSIFICAR EVIDÊNCIA (obrigatório)
Marque `nivel_evidencia`:
- FORTE: há sintoma/queixa explícita (A) OU objetivo de compra/categoria explícita (B) OU “agora” (C).
- FRACA: NÃO há sintoma, mas há contexto de uso/compra plausível e não-médico (ex.: viagem, praia/sol, mosquito, bebê/criança, academia, calor, “me dá água”, “vou dirigir”, “vai chover”, “vai acampar”).
- NENHUMA: não há nada além de conversa/ruído.

Você DEVE preencher `evidencias[]` com o trecho exato que disparou (tipo A/B/C ou tipo X para contexto FRACO).
Se NENHUMA: `deve_sugerir=false` e retorne item nulo padrão.

PASSO 2 — REGRAS POR NÍVEL
1) Se FORTE:
- Se for APENAS TOSSE/GARGANTA (cof/tosse): use allowlist e máx 2.
- Se for APENAS RINITE/RESFRIADO (atchim/espirro): use allowlist e máx 2.
- Se for APENAS NÁUSEA: use allowlist e máx 2.
- Se for MOLEZA/FADIGA literal: use allowlist e até 3.
- Se for “dor” literal (ex.: dor nas costas/cabeça): pode sugerir até 3 entre: analgesico_isento (genérico), gel tópico para dor, compressa quente/fria (sem dose).
- Se for ferida/unha/ralado/corte literal: pode sugerir: antisséptico tópico, curativo, gaze/micropore (sem dose).

2) Se FRACA:
- Sugira no máximo 1–2 itens SOMENTE da SAFE-ADDON LIST (abaixo), escolhendo os mais alinhados ao contexto.
- SAFE-ADDON LIST (baixo risco): protetor_solar, repelente, curativo, antisseptico_topico, lenço_de_papel, alcool_gel, soro_fisiologico, hidratante_labial, gaze_micropore, hidratante_pele.
- Não sugerir medicamentos “de sintoma” (analgésico/anti-inflamatório/etc.) em evidência fraca.

REGRAS DE CESTA
- Itens complementares (oral/tópico/suporte) e sem repetir classe.
- `sugestao` deve ser nome genérico/categoria (sem marca).
- `tag` deve ser o rótulo mais próximo do enum; se não encaixar, use `outros`.

FORMATO (obrigatório)
Retorne JSON estrito no schema:
- `deve_sugerir`: true/false
- `evidencias`: lista (pode ser vazia)
- `itens`: 1 a 3 itens
Se `deve_sugerir=false` OU `evidencias` vazia, retorne exatamente:
itens: [{"sugestao": null, "explicacao": "Sem sugestão", "tag":"sem_sugestao"}]
""".strip()

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "cesta_farmacia_v26_tag_grande",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "deve_sugerir": { "type": "boolean" },
                "evidencias": {
                    "type": "array",
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "tipo": { "type": "string", "enum": ["A", "B", "C"] },
                            "trecho": { "type": "string", "minLength": 1, "maxLength": 300 }
                        },
                        "required": ["tipo", "trecho"]
                    }
                },
                "itens": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "sugestao": { "type": ["string", "null"], "minLength": 1, "maxLength": 60 },
                            "explicacao": { "type": "string", "minLength": 1, "maxLength": 220 },
                            "tag": {
                                "type": "string",
                                "enum": [
                                    "sem_sugestao",
                                    "outros",
                                    "suporte",
                                    "higiene_pessoal",
                                    "higiene_oral",
                                    "higiene_intima",
                                    "primeiros_socorros",
                                    "pele_feridas",
                                    "antisseptico_topico",
                                    "curativos",
                                    "queimaduras",
                                    "picadas_insetos",
                                    "repelente",
                                    "protetor_solar",
                                    "pos_sol",
                                    "hidratacao_pele",
                                    "protetor_labial",
                                    "assaduras",
                                    "acne_oleosidade",
                                    "cabelo_couro_cabeludo",
                                    "olhos_irritacao",
                                    "ouvido_cuidados",
                                    "nariz_sinus",
                                    "garganta_tosse",
                                    "rinite_resfriado",
                                    "gripe_febre",
                                    "dor_generica",
                                    "dor_cabeca",
                                    "dor_muscular",
                                    "dor_articular",
                                    "contusao_torção",
                                    "termoterapia",
                                    "gastro_digestivo",
                                    "azia_refluxo",
                                    "diarreia",
                                    "constipacao",
                                    "nausea",
                                    "hidratacao_reidratacao",
                                    "ressaca",
                                    "alergia",
                                    "dermatite_coceira",
                                    "fungos_micose",
                                    "herpes_labial",
                                    "saude_feminina",
                                    "saude_masculina",
                                    "gestacao_lactacao_suporte",
                                    "criancas_bebe",
                                    "idoso_suporte",
                                    "vitaminas_minerais",
                                    "imunidade",
                                    "energia_fadiga",
                                    "sono_relaxamento_suporte",
                                    "estresse_ansiedade_suporte",
                                    "performance_esportiva_suporte",
                                    "controle_peso_suporte",
                                    "diabetes_suporte_nao_rx",
                                    "pressao_arterial_suporte",
                                    "colesterol_suporte",
                                    "circulacao_suporte",
                                    "ortopedia_acessorios",
                                    "compressas",
                                    "meias_compressao",
                                    "inalacao_nebulizacao_suporte",
                                    "soro_fisiologico_suporte",
                                    "equipamentos_saude",
                                    "testes_rapidos",
                                    "medicao_temperatura",
                                    "medicao_pressao",
                                    "medicao_glicemia",
                                    "preservativos",
                                    "lubrificantes",
                                    "planejamento_familiar_suporte"
                                ]
                            }
                        },
                        "required": ["sugestao", "explicacao", "tag"]
                    }
                }
            },
            "required": ["deve_sugerir", "evidencias", "itens"]
        }
    }
}
