# Library REST API

Flask + SQLAlchemy + SQLite. Manages books, users and loans.

## Run

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                 # http://127.0.0.1:5000
pytest -q                     # tests
```

Optional variable: `DATABASE_URL` (e.g. `postgresql://user:pass@host/db`).

## Endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/books` | Create a book `{title, author, isbn, copies?}` |
| GET | `/books` | List (`q`, `available=true`, `page`, `per_page`) |
| GET/PUT/DELETE | `/books/<id>` | Retrieve / update / delete |
| POST | `/users` | Create a user `{name, email}` |
| GET | `/users` | List (`q`, pagination) |
| GET/PUT/DELETE | `/users/<id>` | Retrieve / update / delete |
| GET | `/users/<id>/loans` | User's loans (`active=true`) |
| POST | `/loans` | Lend a book `{user_id, book_id, days?}` |
| GET | `/loans` | List (`active`, `overdue`, `user_id`, `book_id`) |
| GET | `/loans/<id>` | Retrieve |
| POST | `/loans/<id>/return` | Return a book |
| POST | `/loans/<id>/renew` | Renew `{days?}` |

## Business rules

- Default loan period is 14 days (max. 60); each user may have at most 3 active loans.
- A book cannot be lent if no copies are available, if the same user already has a copy of it, or if the user has an overdue loan.
- Overdue loans cannot be renewed.
- Books and users that have loans (active or past) cannot be deleted (409).
- Stock is decremented atomically in the database.

## Example

```bash
curl -X POST localhost:5000/books -H 'Content-Type: application/json' \
  -d '{"title":"Dom Casmurro","author":"Machado de Assis","isbn":"978-85","copies":2}'
curl -X POST localhost:5000/users -H 'Content-Type: application/json' \
  -d '{"name":"Ana","email":"ana@ex.com"}'
curl -X POST localhost:5000/loans -H 'Content-Type: application/json' \
  -d '{"user_id":1,"book_id":1,"days":14}'
```

## Suggested next steps

Authentication (JWT) and roles (librarian/reader), late fees, Alembic migrations, Docker.
