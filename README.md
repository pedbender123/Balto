🤖 Balto Server Backend

Sistema de Inteligência Farmacêutica em Tempo Real

O Balto Server é um serviço de backend assíncrono de alta performance desenvolvido em Python. Ele atua como o cérebro da operação, orquestrando o reconhecimento de fala, processamento de linguagem natural e a lógica de sugestão farmacêutica.

📋 Stack Tecnológica

Linguagem: Python 3.10

Server: AIOHTTP (Async/WebSockets)

VAD (Voice Activity Detection): WebRTCVAD + Energy Gate (Filtragem avançada de ruído/silêncio)

STT (Speech-to-Text): ElevenLabs (Scribe)

LLM (Inteligência): xAI (Grok Beta)

Banco de Dados: SQLite (Gerenciado via SQLAlchemy/Direct Access)

Infraestrutura: Docker & Docker Compose

✨ Novidades e Funcionalidades

1. 🛡️ Nova Área Administrativa

O sistema agora conta com um painel de administração integrado para gestão e auditoria.

Monitoramento em Tempo Real: Visualize o status do serviço e conexões ativas.

Histórico de Transações: Acesso completo aos logs de sugestões, transcrições e produtos recomendados.

Ajuste Fino: Capacidade de verificar a precisão das transcrições e das respostas da IA.

2. 🚀 Pipeline de IA Otimizada

Processamento de Áudio: O VAD foi recalibrado para ignorar ruídos de farmácia (bips, impressoras) e focar na voz humana.

Grok Beta: Integração atualizada com o modelo xAI para respostas mais rápidas e contextualizadas com bula de medicamentos.

📡 Endereços de Acesso (Endpoints)

O backend pode ser acessado localmente (desenvolvimento) ou através da VPS de produção.

Ambiente

URL Base (HTTP/Admin)

WebSocket (WSS/WS)

Descrição

Produção (VPS)

https://balto.pbpmdev.com

wss://balto.pbpmdev.com/ws

Ambiente estável com SSL.

Local (Dev)

http://localhost:8765

ws://localhost:8765/ws

Para testes e desenvolvimento.

Nota: Ao usar a VPS (https), certifique-se de que seu cliente WebSocket utilize wss:// (Secure WebSocket) para evitar erros de conteúdo misto.

🚀 Instalação e Execução

1. Configuração de Variáveis (.env)

Crie um arquivo .env na pasta backend/ baseando-se no modelo abaixo:

XAI_API_KEY="sua-chave-grok-aqui"
ELEVENLABS_API_KEY="sua-chave-elevenlabs-aqui"
DB_FILE="/backend/app/dados/registro.db"
VAD_ENERGY_THRESHOLD=300
ADMIN_SECRET=x9PeHTY7ouQNvzJH
MOCK_MODE=0
AUDIO_DUMP_DIR=/backend/app/audio_dumps

2. Rodando com Docker (Recomendado)

Utilize o Docker Compose para subir a aplicação. O volume balto-dados garante que seu banco de dados persista mesmo após reiniciar os containers.

Iniciar o serviço:

docker-compose up --build -d


Verificar logs em tempo real:

docker-compose logs -f


Parar o serviço:

docker-compose down


🔌 Protocolo WebSocket

O cliente deve se conectar ao endpoint /ws e seguir o fluxo abaixo.

1. Autenticação (Cliente -> Servidor)

Imediatamente após conectar, envie:

{
  "comando": "auth",
  "api_key": "sua-api-key-do-balcao"
}


2. Streaming de Áudio (Cliente -> Servidor)

Envie o áudio em formato binário continuamente:

Formato: PCM 16-bit, 16kHz, Mono.

Chunk Size: Idealmente frames de 20ms a 30ms.

Otimização: O servidor possui Silence Suppression. Áudios contendo apenas silêncio ou ruído estático são descartados antes de gerar custos nas APIs de STT/LLM.

3. Recebimento de Sugestões (Servidor -> Cliente)

Quando o sistema detecta uma oportunidade de venda ou necessidade de intervenção:

{
  "comando": "recomendar",
  "produto": "Vitamina C 1g",
  "explicacao": "Cliente relatou sintomas de gripe e fadiga.",
  "transcricao_base": "Estou me sentindo muito cansado e gripado ultimamente.",
  "confianca": "alta"
}


🛠️ Manutenção e Banco de Dados

Localização: O banco SQLite fica salvo no volume Docker e mapeado internamente em /backend/app/dados/registro.db.

Backups: Para realizar backup, copie o arquivo .db do volume ou utilize a nova interface Admin para exportar os dados relevantes.

📂 Estrutura de Pastas

/
├── backend/
│   ├── app/
│   │   ├── admin/       # Rotas e templates da Área Admin
│   │   ├── core/        # Lógica de VAD e WebSocket
│   │   ├── services/    # Integrações (ElevenLabs, xAI)
│   │   └── main.py      # Entrypoint
│   ├── Dockerfile
│   └── .env
├── docker-compose.yml
└── README.md
