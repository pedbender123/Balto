# Acesso ao Banco de Dados (Balto Server)

Este documento explica como acessar o banco de dados PostgreSQL rodando no servidor Balto para inspeção direta.

## 1. Acesso via Linha de Comando (SSH)

O banco de dados roda dentro de um container Docker chamado `balto-postgres-service`. Para acessá-lo:

1.  Conecte-se ao VPS via SSH:
    ```bash
    ssh root@<IP_DO_SERVIDOR>
    ```

2.  Execute o cliente Postgres (`psql`) dentro do container:
    ```bash
    docker exec -it balto-postgres-service psql -U balto_user -d balto_db
    ```

3.  Agora você está no prompt do SQL. Comandos úteis:
    - `\dt`: Listar tabelas.
    - `SELECT * FROM interacoes ORDER BY timestamp DESC LIMIT 5;`: Ver as 5 últimas interações.
    - `\d interacoes`: Ver o schema da tabela interações.
    - `\q`: Sair.

## 2. Acesso Externo (Opcional/Debug)

O banco expõe a porta **5433** no servidor (mapeada para a 5432 interna).

- **Host**: `72.61.133.109` (ou `balto.pbpmdev.com` se configurado)
- **Porta**: `5433`
- **Database**: `balto_db`
- **User**: `balto_user`
- **Password**: `baltopassword123`

> [!WARNING]
> Certifique-se de que o firewall do servidor permita conexões na porta 5433 se precisar acessar de sua máquina local (ex: via DBeaver ou pgAdmin). Por segurança, recomenda-se usar túnel SSH.

### Exemplo de Túnel SSH (Recomendado)
Em vez de abrir a porta 5433 para o mundo, crie um túnel:
```bash
ssh -L 5434:localhost:5433 root@72.61.133.109
```
Depois conecte seu DBeaver em `localhost:5434`.
