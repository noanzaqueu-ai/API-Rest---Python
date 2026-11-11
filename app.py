"""API REST de biblioteca: livros, usuários e empréstimos (Flask + SQLAlchemy)."""
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey, String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MAX_ACTIVE_LOANS = 3
DEFAULT_LOAN_DAYS = 14
MAX_LOAN_DAYS = 60


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


# ----------------------------------------------------------------- modelos
class BaseModel(db.Model):
    """Base abstrata; o __init__ tipado permite Book(title=...) sem alertas do checker."""

    __abstract__ = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class Book(BaseModel):
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    author: Mapped[str] = mapped_column(String(200))
    isbn: Mapped[str] = mapped_column(String(20), unique=True)
    copies_total: Mapped[int] = mapped_column(default=1)
    copies_available: Mapped[int] = mapped_column(default=1)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "isbn": self.isbn,
            "copies_total": self.copies_total,
            "copies_available": self.copies_available,
        }


class User(BaseModel):
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }


class Loan(BaseModel):
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    loaned_at: Mapped[datetime] = mapped_column(default=utcnow)
    due_at: Mapped[datetime] = mapped_column()
    returned_at: Mapped[datetime | None] = mapped_column(default=None)

    book: Mapped[Book] = relationship()
    user: Mapped[User] = relationship()

    @property
    def active(self):
        return self.returned_at is None

    @property
    def overdue(self):
        return self.active and utcnow() > self.due_at

    def to_dict(self):
        return {
            "id": self.id,
            "book_id": self.book_id,
            "user_id": self.user_id,
            "loaned_at": self.loaned_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "returned_at": self.returned_at.isoformat() if self.returned_at else None,
            "active": self.active,
            "overdue": self.overdue,
        }


# ----------------------------------------------------------------- helpers
class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Corpo JSON inválido ou ausente.")
    return data


def require_str(data, field, max_len=200):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(f"Campo '{field}' é obrigatório e deve ser texto.")
    value = value.strip()
    if len(value) > max_len:
        raise ApiError(f"Campo '{field}' excede {max_len} caracteres.")
    return value


def require_int(data, field, minimum=None, default=None):
    value = data.get(field, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(f"Campo '{field}' é obrigatório e deve ser inteiro.")
    if minimum is not None and value < minimum:
        raise ApiError(f"Campo '{field}' deve ser >= {minimum}.")
    return value


def paginate(query):
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", 20, type=int), 1), 100)
    p = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "items": [i.to_dict() for i in p.items],
        "page": p.page,
        "per_page": per_page,
        "total": p.total,
        "pages": p.pages,
    }


def get_or_404(model, ident):
    obj = db.session.get(model, ident)
    if obj is None:
        raise ApiError(f"{model.__name__} {ident} não encontrado.", 404)
    return obj


# ------------------------------------------------------------------- app
def create_app(config=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///library.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if config:
        app.config.update(config)
    db.init_app(app)
    with app.app_context():
        db.create_all()

    @app.errorhandler(ApiError)
    def handle_api_error(e):
        return jsonify(error=e.message), e.status

    @app.errorhandler(404)
    def handle_404(_):
        return jsonify(error="Rota não encontrada."), 404

    @app.errorhandler(405)
    def handle_405(_):
        return jsonify(error="Método não permitido."), 405

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    # ------------------------------------------------------------ livros
    @app.post("/books")
    def create_book():
        data = body()
        copies = require_int(data, "copies", minimum=1, default=1)
        book = Book(
            title=require_str(data, "title"),
            author=require_str(data, "author"),
            isbn=require_str(data, "isbn", 20),
            copies_total=copies,
            copies_available=copies,
        )
        db.session.add(book)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise ApiError("Já existe um livro com esse ISBN.", 409)
        return jsonify(book.to_dict()), 201

    @app.get("/books")
    def list_books():
        q = Book.query
        if s := request.args.get("q"):
            like = f"%{s}%"
            q = q.filter(Book.title.ilike(like) | Book.author.ilike(like))
        if request.args.get("available") in ("1", "true"):
            q = q.filter(Book.copies_available > 0)
        return jsonify(paginate(q.order_by(Book.title)))

    @app.get("/books/<int:book_id>")
    def get_book(book_id):
        return jsonify(get_or_404(Book, book_id).to_dict())

    @app.put("/books/<int:book_id>")
    def update_book(book_id):
        book = get_or_404(Book, book_id)
        data = body()
        if "title" in data:
            book.title = require_str(data, "title")
        if "author" in data:
            book.author = require_str(data, "author")
        if "isbn" in data:
            book.isbn = require_str(data, "isbn", 20)
        if "copies" in data:
            new_total = require_int(data, "copies", minimum=1)
            on_loan = book.copies_total - book.copies_available
            if new_total < on_loan:
                raise ApiError(
                    f"Há {on_loan} exemplares emprestados; total não pode ser menor.", 409
                )
            book.copies_total = new_total
            book.copies_available = new_total - on_loan
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise ApiError("Já existe um livro com esse ISBN.", 409)
        return jsonify(book.to_dict())

    @app.delete("/books/<int:book_id>")
    def delete_book(book_id):
        book = get_or_404(Book, book_id)
        if Loan.query.filter_by(book_id=book.id, returned_at=None).count():
            raise ApiError("Livro possui empréstimos ativos.", 409)
        if Loan.query.filter_by(book_id=book.id).count():
            raise ApiError("Livro possui histórico de empréstimos.", 409)
        db.session.delete(book)
        db.session.commit()
        return "", 204

    # ---------------------------------------------------------- usuários
    @app.post("/users")
    def create_user():
        data = body()
        email = require_str(data, "email").lower()
        if "@" not in email:
            raise ApiError("E-mail inválido.")
        user = User(name=require_str(data, "name", 120), email=email)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise ApiError("Já existe um usuário com esse e-mail.", 409)
        return jsonify(user.to_dict()), 201

    @app.get("/users")
    def list_users():
        q = User.query
        if s := request.args.get("q"):
            like = f"%{s}%"
            q = q.filter(User.name.ilike(like) | User.email.ilike(like))
        return jsonify(paginate(q.order_by(User.name)))

    @app.get("/users/<int:user_id>")
    def get_user(user_id):
        return jsonify(get_or_404(User, user_id).to_dict())

    @app.put("/users/<int:user_id>")
    def update_user(user_id):
        user = get_or_404(User, user_id)
        data = body()
        if "name" in data:
            user.name = require_str(data, "name", 120)
        if "email" in data:
            email = require_str(data, "email").lower()
            if "@" not in email:
                raise ApiError("E-mail inválido.")
            user.email = email
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise ApiError("Já existe um usuário com esse e-mail.", 409)
        return jsonify(user.to_dict())

    @app.delete("/users/<int:user_id>")
    def delete_user(user_id):
        user = get_or_404(User, user_id)
        if Loan.query.filter_by(user_id=user.id).count():
            raise ApiError("Usuário possui empréstimos registrados.", 409)
        db.session.delete(user)
        db.session.commit()
        return "", 204

    @app.get("/users/<int:user_id>/loans")
    def user_loans(user_id):
        get_or_404(User, user_id)
        q = Loan.query.filter_by(user_id=user_id)
        if request.args.get("active") in ("1", "true"):
            q = q.filter(Loan.returned_at.is_(None))
        return jsonify(paginate(q.order_by(Loan.loaned_at.desc())))

    # -------------------------------------------------------- empréstimos
    @app.post("/loans")
    def create_loan():
        data = body()
        user = get_or_404(User, require_int(data, "user_id"))
        book = get_or_404(Book, require_int(data, "book_id"))
        days = require_int(data, "days", minimum=1, default=DEFAULT_LOAN_DAYS)
        if days > MAX_LOAN_DAYS:
            raise ApiError(f"Prazo máximo é {MAX_LOAN_DAYS} dias.")

        active = Loan.query.filter_by(user_id=user.id, returned_at=None)
        if active.count() >= MAX_ACTIVE_LOANS:
            raise ApiError(f"Limite de {MAX_ACTIVE_LOANS} empréstimos ativos atingido.", 409)
        if active.filter_by(book_id=book.id).count():
            raise ApiError("Usuário já está com um exemplar deste livro.", 409)
        if any(l.overdue for l in active.all()):
            raise ApiError("Usuário possui empréstimo em atraso.", 409)

        # decremento atômico: evita estourar o estoque em requisições concorrentes
        updated = Book.query.filter(
            Book.id == book.id, Book.copies_available > 0
        ).update({Book.copies_available: Book.copies_available - 1})
        if not updated:
            db.session.rollback()
            raise ApiError("Sem exemplares disponíveis.", 409)

        loan = Loan(user_id=user.id, book_id=book.id, due_at=utcnow() + timedelta(days=days))
        db.session.add(loan)
        db.session.commit()
        return jsonify(loan.to_dict()), 201

    @app.get("/loans")
    def list_loans():
        q = Loan.query
        if request.args.get("active") in ("1", "true"):
            q = q.filter(Loan.returned_at.is_(None))
        if request.args.get("overdue") in ("1", "true"):
            q = q.filter(Loan.returned_at.is_(None), Loan.due_at < utcnow())
        if (uid := request.args.get("user_id", type=int)) is not None:
            q = q.filter_by(user_id=uid)
        if (bid := request.args.get("book_id", type=int)) is not None:
            q = q.filter_by(book_id=bid)
        return jsonify(paginate(q.order_by(Loan.loaned_at.desc())))

    @app.get("/loans/<int:loan_id>")
    def get_loan(loan_id):
        return jsonify(get_or_404(Loan, loan_id).to_dict())

    @app.post("/loans/<int:loan_id>/return")
    def return_loan(loan_id):
        loan = get_or_404(Loan, loan_id)
        if not loan.active:
            raise ApiError("Empréstimo já foi devolvido.", 409)
        loan.returned_at = utcnow()
        Book.query.filter_by(id=loan.book_id).update(
            {Book.copies_available: Book.copies_available + 1}
        )
        db.session.commit()
        return jsonify(loan.to_dict())

    @app.post("/loans/<int:loan_id>/renew")
    def renew_loan(loan_id):
        loan = get_or_404(Loan, loan_id)
        if not loan.active:
            raise ApiError("Empréstimo já foi devolvido.", 409)
        if loan.overdue:
            raise ApiError("Empréstimo em atraso não pode ser renovado.", 409)
        days = require_int(request.get_json(silent=True) or {}, "days", minimum=1,
                           default=DEFAULT_LOAN_DAYS)
        if days > MAX_LOAN_DAYS:
            raise ApiError(f"Prazo máximo é {MAX_LOAN_DAYS} dias.")
        loan.due_at = loan.due_at + timedelta(days=days)
        db.session.commit()
        return jsonify(loan.to_dict())

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
