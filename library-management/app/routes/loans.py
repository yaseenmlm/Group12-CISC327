from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from app import store
from app.models.loan import Loan, LOAN_PERIOD_DAYS
from app.models.reservation import active_holds, can_check_out, fulfill_hold
from notification_service import HOLD_READY_SUBJECT, hold_ready_message, send_notification

FINE_PER_DAY = 0.25  # dollars charged per day overdue

loans_bp = Blueprint("loans", __name__, url_prefix="/loans")


def notify_hold_ready(book):
    """Tell the member whose hold a returned copy now covers that it is ready.

    Holds are served in queue order, so after a return the member at position
    ``available_copies`` (1-based) is the one the freed copy is for. Returns
    None when nobody is waiting for it, otherwise the True/False result of
    send_notification (False also when that member no longer exists). A failed
    notification never blocks the return itself.
    """
    holds = active_holds(book.id)
    position = book.available_copies - 1
    if position < 0 or position >= len(holds):
        return None
    member = store.members.get(holds[position].member_id)
    if member is None:
        return False
    message = hold_ready_message(member.name, book.title)
    return send_notification(member.email, HOLD_READY_SUBJECT, message)


@loans_bp.route("", methods=["GET"])
def list_loans():
    results = list(store.loans.values())
    member_id = request.args.get("member_id", type=int)
    book_id = request.args.get("book_id", type=int)
    if member_id is not None:
        results = [l for l in results if l.member_id == member_id]
    if book_id is not None:
        results = [l for l in results if l.book_id == book_id]
    return jsonify([l.to_dict() for l in results])


@loans_bp.route("", methods=["POST"])
def checkout_book():
    data = request.get_json()
    book = store.books.get(data["book_id"])
    if book is None:
        return jsonify({"error": "Book not found"}), 404
    if store.members.get(data["member_id"]) is None:
        return jsonify({"error": "Member not found"}), 404

    if not can_check_out(book, data["member_id"]):
        if book.available_copies <= 0:
            return jsonify({"error": "No copies available"}), 409
        return jsonify({"error": "Book is on hold for another member"}), 409

    book.available_copies -= 1

    loan_id = store.next_id("loan")
    loan = Loan(
        id=loan_id,
        book_id=data["book_id"],
        member_id=data["member_id"],
        due_date=Loan.default_due_date(),
    )
    store.loans[loan_id] = loan
    fulfill_hold(data["book_id"], data["member_id"])
    return jsonify(loan.to_dict()), 201


@loans_bp.route("/<int:loan_id>/return", methods=["PUT"])
def return_book(loan_id):
    loan = store.loans.get(loan_id)
    if loan is None:
        return jsonify({"error": "Loan not found"}), 404
    if loan.return_date is not None:
        return jsonify({"error": "Loan already returned"}), 400

    loan.return_date = date.today()
    book = store.books.get(loan.book_id)
    book.available_copies += 1

    result = loan.to_dict()
    result["hold_notified"] = notify_hold_ready(book)
    return jsonify(result)


@loans_bp.route("/<int:loan_id>/renew", methods=["PUT"])
def renew_loan(loan_id):
    loan = store.loans.get(loan_id)
    if loan is None:
        return jsonify({"error": "Loan not found"}), 404
    if loan.return_date is not None:
        return jsonify({"error": "Loan already returned"}), 400
    if any(h.member_id != loan.member_id for h in active_holds(loan.book_id)):
        return jsonify({"error": "Cannot renew: another member has a hold on this book"}), 409

    loan.due_date = loan.due_date + timedelta(days=LOAN_PERIOD_DAYS)
    return jsonify(loan.to_dict())


@loans_bp.route("/<int:loan_id>/fine", methods=["GET"])
def get_fine(loan_id):
    loan = store.loans.get(loan_id)
    if loan is None:
        return jsonify({"error": "Loan not found"}), 404

    # BUG: always uses date.today() as the end date, even when the book has
    # already been returned. A returned loan should use loan.return_date so
    # the fine is fixed at the moment of return — but that line is missing here.
    end_date = date.today()
    days_overdue = max(0, (end_date - loan.due_date).days)
    fine_amount = round(days_overdue * FINE_PER_DAY, 2)

    return jsonify({"loan_id": loan_id, "fine_amount": fine_amount})
