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



NORMALIZE_INSTRUCTIONS = """
Extraia APENAS entidades úteis: MED, SINT, DOENCA. Ignore preço/quantidade/conversa.

NORMALIZAR só quando for claramente o MESMO item por fonética/grafia (ex: propanol->propranolol; luzartana->losartana; mosaic->imosec). Se não tiver certeza, mantenha RAW (minúsculo, sem acento, sem pontuação).

SINT: só se for um sintoma óbvio (dor, febre, tosse, coriza, coceira, azia, nausea, vomito, diarreia, congestao, ardor, garganta). Caso contrário, NÃO extraia SINT.

FORMATO (1 linha, NUNCA vazio): itens separados por ';' e cada item deve repetir prefixo (MED:xxx; MED:yyy; SINT:zzz...). NÃO use vírgulas. NÃO escreva campos vazios nem 'NADA_RELEVANTE' dentro de SINT/DOENCA.

HINT: escolha 1: DOR, RESP, ALERGIA, GASTRO, DERMATO, FERIDAS, ORL, BOCA, INTIMO, FEMININA, PEDIATRIA, CARDIO, SUPLEMENTOS, NEURO, HIGIENE, OUTRO.

Finalize sempre com ' | HINT'. Se nada relevante: NADA_RELEVANTE | OUTRO.
""".strip()



CLASSIFY_INSTRUCTIONS = """
Você recebe a SAÍDA da etapa 1 no formato: 'MED:...; SINT:...; DOENCA:... | HINT'.

OBJETIVO
1) Retornar TOP_2 macros mais prováveis (ordem importa) dentre as macros permitidas.
2) Retornar micro_categoria mais prováveis (ordem importa) dentre as micros permitidas (MED, SINT/DOENCA); com possibilidade de caso null.
3) Retornar 'ancoras_para_excluir' com os itens MED detectados (em minúsculas, sem acento/pontuação extra), para que o sistema remova da cesta antes de sugerir complementares.

REGRAS DURAS
- NÃO invente itens que não existam no texto de entrada.
- Use HINT como forte sinal para macro.
- Se houver conflito (ex.: MED claramente cardio mas HINT=OUTRO), priorize o MED.
- Se só houver SINT e nenhum MED, as âncoras para excluir devem ser [].
- Se entrada for 'NADA_RELEVANTE | OUTRO': macros_top2=["OUTRO", "OUTRO"], micro=null, ancoras_para_excluir=[].

MACROS PERMITIDAS (use exatamente estes rótulos)
DOR_FEBRE_INFLAMACAO, RESPIRATORIO_GRIPE, ALERGIAS, GASTROINTESTINAL, PELE_DERMATO, FERIDAS_CURATIVOS, OLHOS_OUVIDOS_NARIZ, BOCA_GARGANTA_ODONTO, SAUDE_INTIMA_URINARIO, SAUDE_FEMININA_MENSTRUACAO, PEDIATRIA, CARDIO_PRESSAO, ENDOCRINO_METABOLICO, SUPLEMENTOS, NEURO_PSIQUIATRIA_SONO, HIGIENE_CUIDADOS_PESSOAIS_HPPC, OUTRO

MICROS POR MACRO (opcional) — use APENAS se tiver muita certeza.
Regra: se você retornar micro_categoria, ela DEVE ser um dos rótulos permitidos do macro escolhido (macro1).
Se não tiver certeza alta, use null.

DOR_FEBRE_INFLAMACAO:
- ANALGESICOS_ANTITERMICOS
- ANTIINFLAMATORIOS_AINE
- RELAXANTES_MUSCULARES
- ENXAQUECA
- DOR_ARTICULAR_LOMBAR
- COLICAS_ANTIESPASMODICOS

RESPIRATORIO_GRIPE:
- TOSSE_SECA
- TOSSE_COM_CATARRO
- CONGESTAO_NASAL
- GARGANTA_PASTILHAS_SPRAY
- ANTIGRIPAIS_COMBO
- ASMA_BRONCO_INALADORES

ALERGIAS:
- RINITE_ANTIHISTAMINICO
- ALERGIA_OCULAR
- URTICARIA_COCEIRA
- DERMATITE_ALERGICA_TOPICOS
- PICADAS_INSETO_ALIVIO_LOCAL

GASTROINTESTINAL:
- VERMINOSE_ANTIPARASITARIO
- AZIA_REFLUXO_ANTIACIDO_IBP
- NAUSEA_VOMITO_ANTIEMETICO
- DIARREIA_REIDRATACAO
- PRISAO_DE_VENTRE_LAXANTES
- GASES_SIMETICONA
- DOR_ABDOMINAL_ANTIESPASMODICO
- HEMORROIDA_FISSURA_ANAL

PELE_DERMATO:
- PEDICULOSE_PIOLHO
- ACNE_PELE_OLEOSA
- MICOSE_ANTIFUNGICO_TOPICO
- HERPES_LABIAL_ANTIVIRAL_TOPICO
- ASSADURA_BARREIRA
- RESSECAMENTO_ATOPIA_HIDRATACAO
- QUEIMADURA_LEVE_POS_SOL

FERIDAS_CURATIVOS:
- ANTISSEPTICOS
- CURATIVOS_MATERIAIS
- CICATRIZANTES
- HEMATOMAS_CONTUSOES_ALIVIO_LOCAL
- CALOS_BOLHAS_PES
- PRIMEIROS_SOCORROS_BASICOS

OLHOS_OUVIDOS_NARIZ:
- CONJUNTIVITE_IRRITACAO
- OLHO_SECO_COLIRIO_LUBRIFICANTE
- IRRITACAO_COCEIRA_OCULAR
- COLIRIO_TRATAMENTO_PRESCRICAO
- OUVIDO_GOTAS_TRATAMENTO
- HIGIENE_NASAL_SORO_IRRIGACAO
- SPRAY_NASAL_MEDICAMENTOSO

BOCA_GARGANTA_ODONTO:
- AFTAS_LESOES_ORAIS
- DOR_DE_DENTE_INFECCAO_SUSPEITA
- ANTISSEPTICO_BUCAL_ENXAGUANTE
- CREME_DENTAL_SENSIBILIDADE
- FIO_DENTAL_ESCOVAS
- HALITO_CUIDADOS_ORAIS

SAUDE_INTIMA_URINARIO:
- DISFUNCAO_ERETIL
- CANDIDIASE_TRATAMENTO
- HIGIENE_INTIMA_IRRITACAO
- SINTOMAS_URINARIOS_ARDOR
- INCONTINENCIA_ABSORVENTE_GERIATRICO
- PRESERVATIVOS_LUBRIFICANTES
- TESTE_GRAVIDEZ

SAUDE_FEMININA_MENSTRUACAO:
- MENSTRUACAO_ABSORVENTES
- COLICA_MENSTRUAL
- TPM_SINTOMAS
- MENOPAUSA_RESSECAMENTO
- ANTICONCEPCIONAL_USO_CONTINUO

PEDIATRIA:
- FEBRE_INFANTIL
- RESFRIADO_TOSSE_INFANTIL
- COLICAS_GASES_BEBE
- DERMATITE_FRALDA
- VITAMINAS_INFANTIS

CARDIO_PRESSAO:
- HIPERTENSAO_MEDICAMENTOS
- COLESTEROL_ESTATINAS

ENDOCRINO_METABOLICO:
- DIABETES_MEDICAMENTOS

SUPLEMENTOS:
- OSSO_CALCIO_VITAMINA_D
- ANEMIA_FERRO_B12
- VITAMINAS_GERAIS_IMUNIDADE
- GESTAO_DE_PESO

NEURO_PSIQUIATRIA_SONO:
- ANSIEDADE_CALMANTE
- INSONIA_SONO

HIGIENE_CUIDADOS_PESSOAIS_HPPC:
- REPELENTES_PICADAS
- PROTETOR_SOLAR_FOTOPROTECAO

Se macro1 for OUTRO, micro_categoria DEVE ser null.

SAÍDA
Responda APENAS com JSON válido em uma linha, sem texto extra.
Formato:
{"macros_top2":["...","..."],"micro_categoria":null,"ancoras_para_excluir":["..."]}
""".strip()