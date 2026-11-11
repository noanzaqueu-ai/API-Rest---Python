# API REST de Biblioteca

Flask + SQLAlchemy + SQLite. Gerencia livros, usuários e empréstimos.

## Executar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py                 # http://127.0.0.1:5000
pytest -q                     # testes
```

Variável opcional: `DATABASE_URL` (ex.: `postgresql://user:pass@host/db`).

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Healthcheck |
| POST | `/books` | Cria livro `{title, author, isbn, copies?}` |
| GET | `/books` | Lista (`q`, `available=true`, `page`, `per_page`) |
| GET/PUT/DELETE | `/books/<id>` | Detalhe / atualiza / remove |
| POST | `/users` | Cria usuário `{name, email}` |
| GET | `/users` | Lista (`q`, paginação) |
| GET/PUT/DELETE | `/users/<id>` | Detalhe / atualiza / remove |
| GET | `/users/<id>/loans` | Empréstimos do usuário (`active=true`) |
| POST | `/loans` | Empresta `{user_id, book_id, days?}` |
| GET | `/loans` | Lista (`active`, `overdue`, `user_id`, `book_id`) |
| GET | `/loans/<id>` | Detalhe |
| POST | `/loans/<id>/return` | Devolve |
| POST | `/loans/<id>/renew` | Renova `{days?}` |

## Regras de negócio

- Prazo padrão de 14 dias (máx. 60); máximo de 3 empréstimos ativos por usuário.
- Não é possível emprestar sem exemplares disponíveis, o mesmo livro duas vezes ao mesmo usuário, nem a quem tem empréstimo em atraso.
- Empréstimo em atraso não pode ser renovado.
- Livro/usuário com empréstimos (ativos ou históricos) não podem ser removidos (409).
- O estoque é decrementado de forma atômica no banco.

## Exemplo

```bash
curl -X POST localhost:5000/books -H 'Content-Type: application/json' \
  -d '{"title":"Dom Casmurro","author":"Machado de Assis","isbn":"978-85","copies":2}'
curl -X POST localhost:5000/users -H 'Content-Type: application/json' \
  -d '{"name":"Ana","email":"ana@ex.com"}'
curl -X POST localhost:5000/loans -H 'Content-Type: application/json' \
  -d '{"user_id":1,"book_id":1,"days":14}'
```

## Próximos passos sugeridos

Autenticação (JWT) e papéis (bibliotecário/leitor), multas por atraso, migrações com Alembic, Docker.
