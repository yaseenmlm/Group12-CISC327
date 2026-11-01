from datetime import date

from flask import Blueprint, redirect, render_template, request, url_for

from app import store
from app.models.book import Book
from app.models.loan import Loan
from app.models.member import Member
from app.models.reservation import can_check_out, fulfill_hold

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
def home():
    return render_template("home.html")


@views_bp.route("/ui/books", methods=["GET", "POST"])
def books_page():
    if request.method == "POST":
        total_copies = int(request.form["total_copies"])
        book_id = store.next_id("book")
        book = Book(
            id=book_id,
            title=request.form["title"],
            author=request.form["author"],
            isbn=request.form["isbn"],
            total_copies=total_copies,
            available_copies=total_copies,
        )
        store.books[book_id] = book
        return redirect(url_for("views.books_page"))
    return render_template("books.html", books=store.books.values())


@views_bp.route("/ui/books/<int:book_id>/delete", methods=["POST"])
def delete_book_page(book_id):
    store.books.pop(book_id, None)
    return redirect(url_for("views.books_page"))


@views_bp.route("/ui/members", methods=["GET", "POST"])
def members_page():
    if request.method == "POST":
        member_id = store.next_id("member")
        member = Member(id=member_id, name=request.form["name"], email=request.form["email"])
        store.members[member_id] = member
        return redirect(url_for("views.members_page"))
    return render_template("members.html", members=store.members.values())


@views_bp.route("/ui/members/<int:member_id>/delete", methods=["POST"])
def delete_member_page(member_id):
    store.members.pop(member_id, None)
    return redirect(url_for("views.members_page"))


@views_bp.route("/ui/loans", methods=["GET", "POST"])
def loans_page():
    if request.method == "POST":
        book_id = int(request.form["book_id"])
        member_id = int(request.form["member_id"])
        book = store.books.get(book_id)
        if book is not None and can_check_out(book, member_id):
            book.available_copies -= 1
            loan_id = store.next_id("loan")
            loan = Loan(
                id=loan_id,
                book_id=book_id,
                member_id=member_id,
                due_date=Loan.default_due_date(),
            )
            store.loans[loan_id] = loan
            fulfill_hold(book_id, member_id)
        return redirect(url_for("views.loans_page"))
    return render_template("loans.html", loans=store.loans.values())


@views_bp.route("/ui/loans/<int:loan_id>/return", methods=["POST"])
def return_loan_page(loan_id):
    loan = store.loans.get(loan_id)
    if loan is not None and loan.return_date is None:
        loan.return_date = date.today()
        book = store.books.get(loan.book_id)
        if book is not None:
            book.available_copies += 1
    return redirect(url_for("views.loans_page"))
