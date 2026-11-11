from datetime import timedelta

import pytest

from app import Loan, create_app, db, utcnow


@pytest.fixture
def app():
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def mk_book(c, isbn="111", copies=1, title="Dom Casmurro"):
    r = c.post("/books", json={"title": title, "author": "Machado de Assis",
                               "isbn": isbn, "copies": copies})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def mk_user(c, email="ana@ex.com"):
    r = c.post("/users", json={"name": "Ana", "email": email})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_book_crud_and_validation(client):
    assert client.post("/books", json={"title": "x"}).status_code == 400
    b = mk_book(client)
    assert client.post("/books", json={"title": "o", "author": "a", "isbn": "111"}).status_code == 409
    assert client.get(f"/books/{b['id']}").get_json()["title"] == "Dom Casmurro"
    r = client.put(f"/books/{b['id']}", json={"copies": 3})
    assert r.get_json()["copies_available"] == 3
    assert client.get("/books?q=casmurro").get_json()["total"] == 1
    assert client.delete(f"/books/{b['id']}").status_code == 204
    assert client.get(f"/books/{b['id']}").status_code == 404


def test_user_crud(client):
    u = mk_user(client)
    assert client.post("/users", json={"name": "B", "email": "ANA@ex.com"}).status_code == 409
    assert client.post("/users", json={"name": "B", "email": "invalido"}).status_code == 400
    assert client.put(f"/users/{u['id']}", json={"name": "Ana Maria"}).get_json()["name"] == "Ana Maria"
    assert client.delete(f"/users/{u['id']}").status_code == 204


def test_loan_and_return_updates_stock(client):
    b, u = mk_book(client), mk_user(client)
    r = client.post("/loans", json={"user_id": u["id"], "book_id": b["id"]})
    assert r.status_code == 201
    loan = r.get_json()
    assert client.get(f"/books/{b['id']}").get_json()["copies_available"] == 0
    assert client.delete(f"/books/{b['id']}").status_code == 409

    r = client.post(f"/loans/{loan['id']}/return")
    assert r.status_code == 200 and r.get_json()["active"] is False
    assert client.get(f"/books/{b['id']}").get_json()["copies_available"] == 1
    assert client.post(f"/loans/{loan['id']}/return").status_code == 409


def test_no_stock(client):
    b = mk_book(client, copies=1)
    u1, u2 = mk_user(client, "a@a.com"), mk_user(client, "b@b.com")
    assert client.post("/loans", json={"user_id": u1["id"], "book_id": b["id"]}).status_code == 201
    r = client.post("/loans", json={"user_id": u2["id"], "book_id": b["id"]})
    assert r.status_code == 409


def test_loan_limit_and_duplicate(client):
    u = mk_user(client)
    books = [mk_book(client, isbn=str(i)) for i in range(4)]
    for b in books[:3]:
        assert client.post("/loans", json={"user_id": u["id"], "book_id": b["id"]}).status_code == 201
    assert client.post("/loans", json={"user_id": u["id"], "book_id": books[3]["id"]}).status_code == 409
    # duplicado
    u2 = mk_user(client, "z@z.com")
    b = mk_book(client, isbn="dup", copies=2)
    assert client.post("/loans", json={"user_id": u2["id"], "book_id": b["id"]}).status_code == 201
    assert client.post("/loans", json={"user_id": u2["id"], "book_id": b["id"]}).status_code == 409


def test_overdue_blocks_new_loan_and_renew(app, client):
    b1, b2 = mk_book(client, isbn="1"), mk_book(client, isbn="2")
    u = mk_user(client)
    loan = client.post("/loans", json={"user_id": u["id"], "book_id": b1["id"]}).get_json()

    r = client.post(f"/loans/{loan['id']}/renew", json={"days": 7})
    assert r.status_code == 200

    with app.app_context():
        db_loan = db.session.get(Loan, loan["id"])
        assert db_loan is not None
        db_loan.due_at = utcnow() - timedelta(days=1)
        db.session.commit()

    assert client.get("/loans?overdue=true").get_json()["total"] == 1
    assert client.post("/loans", json={"user_id": u["id"], "book_id": b2["id"]}).status_code == 409
    assert client.post(f"/loans/{loan['id']}/renew").status_code == 409


def test_user_loans_listing(client):
    b, u = mk_book(client), mk_user(client)
    client.post("/loans", json={"user_id": u["id"], "book_id": b["id"]})
    r = client.get(f"/users/{u['id']}/loans?active=true").get_json()
    assert r["total"] == 1
    assert client.delete(f"/users/{u['id']}").status_code == 409
