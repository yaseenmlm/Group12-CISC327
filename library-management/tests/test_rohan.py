"""Tests written by Rohan.

Features covered (see Table B in the report):
  Members:       create, list, view, update, delete
  Loans:         renew a loan, calculate a fine
  Reservations:  create a reservation, list/filter reservations
  Web UI:        members page

Conventions
  * ``client``         - fixture from conftest.py (TESTING=True).
  * ``lenient_client`` - same app with TESTING=False so an unhandled exception
                         becomes an HTTP 500 response we can assert on.
"""
from datetime import date, timedelta

import pytest

from app import create_app, store


@pytest.fixture
def lenient_client():
    app = create_app()
    app.config["TESTING"] = False
    store.reset()
    with app.test_client() as c:
        yield c
    store.reset()


def make_book(client, title="Dune", author="Frank Herbert", isbn="111", total_copies=1):
    resp = client.post(
        "/books",
        json={"title": title, "author": author, "isbn": isbn, "total_copies": total_copies},
    )
    assert resp.status_code == 201
    return resp.get_json()


def make_member(client, name="Ann", email="ann@example.com"):
    resp = client.post("/members", json={"name": name, "email": email})
    assert resp.status_code == 201
    return resp.get_json()


def checkout(client, book_id=1, member_id=1):
    resp = client.post("/loans", json={"book_id": book_id, "member_id": member_id})
    assert resp.status_code == 201
    return resp.get_json()


# ---------------------------------------------------------------------------
# Feature: create a member  (R17)
# ---------------------------------------------------------------------------
def test_create_member_returns_fields_and_is_retrievable(client):
    resp = client.post("/members", json={"name": "Ann Lee", "email": "ann@example.com"})

    assert resp.status_code == 201
    member = resp.get_json()
    assert member["id"] == 1
    assert member["name"] == "Ann Lee"
    assert member["email"] == "ann@example.com"
    assert member["membership_date"] == date.today().isoformat()
    assert client.get("/members/1").get_json() == member


def test_create_member_missing_email_creates_nothing(lenient_client):
    resp = lenient_client.post("/members", json={"name": "No Email"})

    assert resp.status_code >= 400
    assert lenient_client.get("/members").get_json() == []


def test_catalog_supports_800_members(client):
    """R17: the system supports at least 800 members."""
    for i in range(800):
        assert client.post(
            "/members", json={"name": f"Member {i}", "email": f"m{i}@example.com"}
        ).status_code == 201

    members = client.get("/members").get_json()
    assert len(members) == 800
    assert members[-1]["id"] == 800


# ---------------------------------------------------------------------------
# Feature: list members, view a member
# ---------------------------------------------------------------------------
def test_list_members_returns_all_created_members_in_order(client):
    make_member(client, "Ann", "a@x.com")
    make_member(client, "Bob", "b@x.com")

    listing = client.get("/members").get_json()

    assert [m["name"] for m in listing] == ["Ann", "Bob"]
    assert [m["id"] for m in listing] == [1, 2]


def test_get_member_unknown_id_returns_404_with_message(client):
    resp = client.get("/members/404")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Member not found"}


# ---------------------------------------------------------------------------
# Feature: update a member
# ---------------------------------------------------------------------------
def test_update_member_changes_name_only_and_persists(client):
    make_member(client, "Ann", "a@x.com")

    resp = client.put("/members/1", json={"name": "Ann Marie"})

    assert resp.status_code == 200
    stored = client.get("/members/1").get_json()
    assert stored["name"] == "Ann Marie"
    assert stored["email"] == "a@x.com"  # untouched
    assert stored["membership_date"] == date.today().isoformat()


def test_update_member_email_then_name_accumulates_changes(client):
    make_member(client, "Ann", "a@x.com")

    client.put("/members/1", json={"email": "new@x.com"})
    client.put("/members/1", json={"name": "Anna"})

    stored = client.get("/members/1").get_json()
    assert (stored["name"], stored["email"]) == ("Anna", "new@x.com")


def test_update_member_unknown_id_returns_404(client):
    resp = client.put("/members/9", json={"name": "x"})
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Member not found"}


# ---------------------------------------------------------------------------
# Feature: delete a member
# ---------------------------------------------------------------------------
def test_delete_member_removes_record_and_second_delete_is_404(client):
    make_member(client)

    assert client.delete("/members/1").status_code == 204
    assert client.get("/members/1").status_code == 404
    assert client.get("/members").get_json() == []
    assert client.delete("/members/1").status_code == 404


def test_delete_member_does_not_affect_other_members(client):
    make_member(client, "Ann", "a@x.com")
    make_member(client, "Bob", "b@x.com")

    client.delete("/members/1")

    assert [m["name"] for m in client.get("/members").get_json()] == ["Bob"]


# ---------------------------------------------------------------------------
# Feature: renew a loan  (R9)
# ---------------------------------------------------------------------------
def test_renew_extends_due_date_by_14_days_and_keeps_loan_open(client):
    make_book(client)
    make_member(client)
    loan = checkout(client)
    original_due = date.fromisoformat(loan["due_date"])

    resp = client.put("/loans/1/renew")

    assert resp.status_code == 200
    renewed = resp.get_json()
    assert date.fromisoformat(renewed["due_date"]) == original_due + timedelta(days=14)
    assert renewed["return_date"] is None
    # persistent: lookup shows the new due date
    assert client.get("/loans?book_id=1").get_json()[0]["due_date"] == renewed["due_date"]


def test_renew_twice_accumulates_28_days_without_changing_availability(client):
    make_book(client, total_copies=1)
    make_member(client)
    loan = checkout(client)

    client.put("/loans/1/renew")
    second = client.put("/loans/1/renew").get_json()

    expected = date.fromisoformat(loan["due_date"]) + timedelta(days=28)
    assert date.fromisoformat(second["due_date"]) == expected
    assert client.get("/books/1").get_json()["available_copies"] == 0


def test_renew_unknown_loan_returns_404(client):
    resp = client.put("/loans/99/renew")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Loan not found"}


def test_renew_returned_loan_is_rejected_and_due_date_unchanged(client):
    make_book(client)
    make_member(client)
    loan = checkout(client)
    client.put("/loans/1/return")

    resp = client.put("/loans/1/renew")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Loan already returned"}
    assert client.get("/loans").get_json()[0]["due_date"] == loan["due_date"]


# ---------------------------------------------------------------------------
# Feature: calculate a fine   ($0.25 per day overdue; see FINE_PER_DAY)
# ---------------------------------------------------------------------------
def _open_loan_due_in(client, days_from_today):
    make_book(client, total_copies=2)
    make_member(client)
    checkout(client)
    store.loans[1].due_date = date.today() + timedelta(days=days_from_today)


def test_fine_is_zero_for_loan_not_yet_due(client):
    _open_loan_due_in(client, 3)
    assert client.get("/loans/1/fine").get_json() == {"loan_id": 1, "fine_amount": 0.0}


def test_fine_is_zero_on_the_due_date_itself(client):
    _open_loan_due_in(client, 0)
    assert client.get("/loans/1/fine").get_json()["fine_amount"] == 0.0


def test_fine_is_25_cents_for_one_day_overdue_and_scales_linearly(client):
    _open_loan_due_in(client, -1)
    assert client.get("/loans/1/fine").get_json()["fine_amount"] == 0.25

    store.loans[1].due_date = date.today() - timedelta(days=10)
    assert client.get("/loans/1/fine").get_json()["fine_amount"] == 2.5


def test_fine_for_unknown_loan_returns_404(client):
    resp = client.get("/loans/5/fine")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Loan not found"}


# ---------------------------------------------------------------------------
# Feature: create a reservation  (R8)
# ---------------------------------------------------------------------------
def _book_on_loan_to_ann(client):
    """Book 1 (single copy) is on loan to member 1; members 2 and 3 also exist."""
    make_book(client, total_copies=1)
    make_member(client, "Ann", "a@x.com")
    make_member(client, "Bob", "b@x.com")
    make_member(client, "Cy", "c@x.com")
    checkout(client, book_id=1, member_id=1)


def test_create_reservation_returns_fields_and_is_listed(client):
    _book_on_loan_to_ann(client)

    resp = client.post("/reservations", json={"book_id": 1, "member_id": 2})

    assert resp.status_code == 201
    reservation = resp.get_json()
    assert reservation["id"] == 1
    assert reservation["book_id"] == 1
    assert reservation["member_id"] == 2
    assert reservation["reservation_date"] == date.today().isoformat()
    assert reservation["fulfilled"] is False
    assert client.get("/reservations").get_json() == [reservation]


def test_create_reservation_unknown_book_returns_404_and_stores_nothing(client):
    make_member(client)
    resp = client.post("/reservations", json={"book_id": 9, "member_id": 1})
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Book not found"}
    assert client.get("/reservations").get_json() == []


def test_create_reservation_unknown_member_returns_404_and_stores_nothing(client):
    make_book(client)
    resp = client.post("/reservations", json={"book_id": 1, "member_id": 9})
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Member not found"}
    assert client.get("/reservations").get_json() == []


# ---------------------------------------------------------------------------
# Feature: list / filter reservations  (R8)
# ---------------------------------------------------------------------------
def test_reservations_keep_first_come_first_served_order(client):
    _book_on_loan_to_ann(client)
    client.post("/reservations", json={"book_id": 1, "member_id": 3})
    client.post("/reservations", json={"book_id": 1, "member_id": 2})

    queue = client.get("/reservations?book_id=1").get_json()

    assert [r["member_id"] for r in queue] == [3, 2]  # Cy asked first
    assert [r["id"] for r in queue] == [1, 2]


def test_reservations_can_be_filtered_by_book_and_by_member(client):
    make_book(client, "A", isbn="1")
    make_book(client, "B", isbn="2")
    make_member(client, "Ann", "a@x.com")
    make_member(client, "Bob", "b@x.com")
    client.post("/reservations", json={"book_id": 1, "member_id": 1})
    client.post("/reservations", json={"book_id": 2, "member_id": 1})
    client.post("/reservations", json={"book_id": 2, "member_id": 2})

    by_book = client.get("/reservations?book_id=2").get_json()
    by_member = client.get("/reservations?member_id=1").get_json()
    both = client.get("/reservations?book_id=2&member_id=2").get_json()

    assert [r["member_id"] for r in by_book] == [1, 2]
    assert [r["book_id"] for r in by_member] == [1, 2]
    assert [(r["book_id"], r["member_id"]) for r in both] == [(2, 2)]


def test_reservation_filter_with_no_match_returns_empty_list(client):
    _book_on_loan_to_ann(client)
    client.post("/reservations", json={"book_id": 1, "member_id": 2})
    assert client.get("/reservations?member_id=3").get_json() == []


# ---------------------------------------------------------------------------
# Feature: web UI - members page
# ---------------------------------------------------------------------------
def test_ui_members_page_is_empty_initially_and_lists_added_member(client):
    first = client.get("/ui/members")
    assert first.status_code == 200
    assert "Ann Lee" not in first.get_data(as_text=True)

    resp = client.post("/ui/members", data={"name": "Ann Lee", "email": "ann@x.com"})

    assert resp.status_code == 302
    assert store.members[1].email == "ann@x.com"
    assert "Ann Lee" in client.get("/ui/members").get_data(as_text=True)


def test_ui_delete_member_removes_member_and_ignores_unknown_ids(client):
    make_member(client, "Ann Lee", "a@x.com")

    assert client.post("/ui/members/1/delete").status_code == 302
    assert store.members == {}
    # deleting an id that does not exist is harmless
    assert client.post("/ui/members/1/delete").status_code == 302
