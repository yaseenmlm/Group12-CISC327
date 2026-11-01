"""Tests written by Yaseen.

Features covered (see Table B in the report):
  Books:  create, list/search, view, update, delete
  Loans:  check out, return, look up loans
  Web UI: home page + books page, loans page

Conventions
  * ``client``         - fixture from conftest.py (TESTING=True, so an unhandled
                         exception inside a route is re-raised in the test).
  * ``lenient_client`` - same app with TESTING=False so an unhandled exception
                         becomes an HTTP 500 response we can assert on.
"""
import time
from datetime import date, timedelta

import pytest

from app import create_app, store
from app.models.book import Book


@pytest.fixture
def lenient_client():
    app = create_app()
    app.config["TESTING"] = False
    store.reset()
    with app.test_client() as c:
        yield c
    store.reset()


def make_book(client, title="Dune", author="Frank Herbert", isbn="111", total_copies=2):
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


# ---------------------------------------------------------------------------
# Feature: create a book  (R13, R17)
# ---------------------------------------------------------------------------
def test_create_book_returns_all_fields_and_is_retrievable(client):
    created = make_book(client, total_copies=3)

    assert created["id"] == 1
    assert created["title"] == "Dune"
    assert created["author"] == "Frank Herbert"
    assert created["isbn"] == "111"
    assert created["total_copies"] == 3
    # a new book starts with every copy available
    assert created["available_copies"] == 3

    # persistent state: the same book comes back from a later GET
    fetched = client.get("/books/1").get_json()
    assert fetched == created


def test_create_book_defaults_to_one_copy_when_total_copies_omitted(client):
    resp = client.post("/books", json={"title": "T", "author": "A", "isbn": "9"})
    assert resp.status_code == 201
    book = resp.get_json()
    assert book["total_copies"] == 1
    assert book["available_copies"] == 1


def test_create_books_assigns_incrementing_ids_and_all_are_listed(client):
    make_book(client, title="First", isbn="1")
    make_book(client, title="Second", isbn="2")

    listing = client.get("/books").get_json()
    assert [b["id"] for b in listing] == [1, 2]
    assert [b["title"] for b in listing] == ["First", "Second"]


def test_create_book_missing_required_field_creates_nothing(lenient_client):
    resp = lenient_client.post("/books", json={"author": "A", "isbn": "2"})  # no title

    assert resp.status_code >= 400  # request must not succeed
    assert lenient_client.get("/books").get_json() == []


def test_catalog_holds_3000_books_and_search_stays_fast(client):
    """R17 (3,000 books) and R12 (search within 3 s)."""
    for i in range(3000):
        store.books[i + 1] = Book(i + 1, f"Title {i}", f"Author {i % 300}", str(i), 1, 1)
    assert len(client.get("/books").get_json()) == 3000

    start = time.perf_counter()
    result = client.get("/books?search=Title 2999").get_json()
    elapsed = time.perf_counter() - start

    assert [b["title"] for b in result] == ["Title 2999"]
    assert elapsed < 3.0


# ---------------------------------------------------------------------------
# Feature: list and search books  (R11, R12, R6)
# ---------------------------------------------------------------------------
def test_list_books_search_matches_title_case_insensitively(client):
    make_book(client, title="Dune", isbn="1")
    make_book(client, title="Emma", author="Jane Austen", isbn="2")

    result = client.get("/books?search=DUNE").get_json()
    assert [b["title"] for b in result] == ["Dune"]


def test_list_books_search_matches_author_and_partial_text(client):
    make_book(client, title="Dune", author="Frank Herbert", isbn="1")
    make_book(client, title="Emma", author="Jane Austen", isbn="2")

    assert [b["title"] for b in client.get("/books?search=herb").get_json()] == ["Dune"]
    assert [b["title"] for b in client.get("/books?search=austen").get_json()] == ["Emma"]


def test_list_books_search_with_no_match_returns_empty_list(client):
    make_book(client)
    resp = client.get("/books?search=zzzz")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_list_books_search_can_return_several_matches(client):
    make_book(client, title="Python Basics", isbn="1")
    make_book(client, title="Advanced Python", isbn="2")
    make_book(client, title="Cooking", author="Chef", isbn="3")

    result = client.get("/books?search=python").get_json()
    assert sorted(b["title"] for b in result) == ["Advanced Python", "Python Basics"]


# ---------------------------------------------------------------------------
# Feature: view one book  (R6, R13)
# ---------------------------------------------------------------------------
def test_get_book_nonexistent_id_returns_404_with_message(client):
    resp = client.get("/books/999")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Book not found"}


def test_get_book_shows_availability_dropping_after_checkout(client):
    make_book(client, total_copies=2)
    make_member(client)
    assert client.get("/books/1").get_json()["available_copies"] == 2

    client.post("/loans", json={"book_id": 1, "member_id": 1})

    book = client.get("/books/1").get_json()
    assert book["available_copies"] == 1
    assert book["total_copies"] == 2


# ---------------------------------------------------------------------------
# Feature: update a book
# ---------------------------------------------------------------------------
def test_update_book_changes_only_supplied_fields_and_persists(client):
    make_book(client, title="Old", author="Writer", isbn="5", total_copies=2)

    resp = client.put("/books/1", json={"title": "New"})
    assert resp.status_code == 200
    assert resp.get_json()["title"] == "New"

    stored = client.get("/books/1").get_json()
    assert stored["title"] == "New"
    assert stored["author"] == "Writer"
    assert stored["isbn"] == "5"
    assert stored["total_copies"] == 2


def test_update_book_nonexistent_id_returns_404(client):
    resp = client.put("/books/42", json={"title": "x"})
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Book not found"}


# ---------------------------------------------------------------------------
# Feature: delete a book
# ---------------------------------------------------------------------------
def test_delete_book_removes_it_and_second_delete_is_404(client):
    make_book(client)

    first = client.delete("/books/1")
    assert first.status_code == 204
    assert client.get("/books/1").status_code == 404
    assert client.get("/books").get_json() == []

    assert client.delete("/books/1").status_code == 404


def test_delete_book_nonexistent_id_returns_404(client):
    assert client.delete("/books/77").status_code == 404


# ---------------------------------------------------------------------------
# Feature: check out a book  (R15, R16, R13)
# ---------------------------------------------------------------------------
def test_checkout_creates_loan_with_14_day_due_date_and_decrements_copies(client):
    make_book(client, total_copies=2)
    make_member(client)

    resp = client.post("/loans", json={"book_id": 1, "member_id": 1})

    assert resp.status_code == 201
    loan = resp.get_json()
    assert loan["id"] == 1
    assert loan["book_id"] == 1
    assert loan["member_id"] == 1
    assert loan["loan_date"] == date.today().isoformat()
    assert loan["due_date"] == (date.today() + timedelta(days=14)).isoformat()
    assert loan["return_date"] is None
    assert client.get("/books/1").get_json()["available_copies"] == 1


def test_checkout_of_every_copy_brings_availability_to_zero(client):
    make_book(client, total_copies=2)
    make_member(client, "Ann", "a@x.com")
    make_member(client, "Bob", "b@x.com")

    client.post("/loans", json={"book_id": 1, "member_id": 1})
    client.post("/loans", json={"book_id": 1, "member_id": 2})

    assert client.get("/books/1").get_json()["available_copies"] == 0
    assert len(client.get("/loans").get_json()) == 2


def test_checkout_nonexistent_book_returns_404_and_records_no_loan(client):
    make_member(client)

    resp = client.post("/loans", json={"book_id": 99, "member_id": 1})

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Book not found"}
    assert client.get("/loans").get_json() == []


# ---------------------------------------------------------------------------
# Feature: return a book  (R15, R16)
# ---------------------------------------------------------------------------
def test_return_restores_copy_sets_return_date_and_keeps_history(client):
    make_book(client, total_copies=1)
    make_member(client)
    client.post("/loans", json={"book_id": 1, "member_id": 1})
    assert client.get("/books/1").get_json()["available_copies"] == 0

    resp = client.put("/loans/1/return")

    assert resp.status_code == 200
    assert resp.get_json()["return_date"] == date.today().isoformat()
    assert client.get("/books/1").get_json()["available_copies"] == 1
    # the returned loan is still on record (R16 - past loan history)
    history = client.get("/loans").get_json()
    assert len(history) == 1
    assert history[0]["return_date"] == date.today().isoformat()


def test_return_twice_is_rejected_and_does_not_add_a_second_copy(client):
    make_book(client, total_copies=1)
    make_member(client)
    client.post("/loans", json={"book_id": 1, "member_id": 1})
    client.put("/loans/1/return")

    second = client.put("/loans/1/return")

    assert second.status_code == 400
    assert second.get_json() == {"error": "Loan already returned"}
    assert client.get("/books/1").get_json()["available_copies"] == 1  # not 2


def test_return_nonexistent_loan_returns_404(client):
    resp = client.put("/loans/55/return")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Loan not found"}


def test_checkout_return_checkout_again_workflow(client):
    """Chained operations: borrow, return, someone else borrows the same copy."""
    make_book(client, total_copies=1)
    make_member(client, "Ann", "a@x.com")
    make_member(client, "Bob", "b@x.com")

    first = client.post("/loans", json={"book_id": 1, "member_id": 1}).get_json()
    client.put(f"/loans/{first['id']}/return")
    second = client.post("/loans", json={"book_id": 1, "member_id": 2}).get_json()

    assert second["id"] == 2
    assert second["member_id"] == 2
    assert client.get("/books/1").get_json()["available_copies"] == 0
    history = client.get("/loans?book_id=1").get_json()
    assert [(l["member_id"], l["return_date"] is None) for l in history] == [(1, False), (2, True)]


# ---------------------------------------------------------------------------
# Feature: look up loans  (R7, R16)
# ---------------------------------------------------------------------------
def test_list_loans_without_filter_returns_every_loan(client):
    make_book(client, "A", isbn="1")
    make_book(client, "B", isbn="2")
    make_member(client)
    client.post("/loans", json={"book_id": 1, "member_id": 1})
    client.post("/loans", json={"book_id": 2, "member_id": 1})

    assert len(client.get("/loans").get_json()) == 2


def test_list_loans_filtered_by_book_id_returns_only_that_books_loans(client):
    make_book(client, "A", isbn="1")
    make_book(client, "B", isbn="2")
    make_member(client)
    client.post("/loans", json={"book_id": 1, "member_id": 1})
    client.post("/loans", json={"book_id": 2, "member_id": 1})

    result = client.get("/loans?book_id=2").get_json()

    assert [l["book_id"] for l in result] == [2]


def test_list_loans_for_unknown_book_id_is_empty(client):
    make_book(client)
    make_member(client)
    client.post("/loans", json={"book_id": 1, "member_id": 1})
    assert client.get("/loans?book_id=500").get_json() == []


# ---------------------------------------------------------------------------
# Feature: web UI - home page, books page, loans page  (R6, R13, R15)
# ---------------------------------------------------------------------------
def test_ui_home_page_links_to_books_members_and_loans(client):
    resp = client.get("/")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "Library Management System" in html
    for path in ("/ui/books", "/ui/members", "/ui/loans"):
        assert f'href="{path}"' in html


def test_ui_add_book_form_creates_book_shown_with_availability(client):
    resp = client.post(
        "/ui/books",
        data={"title": "Emma", "author": "Jane Austen", "isbn": "42", "total_copies": "3"},
    )

    assert resp.status_code == 302  # redirect back to the list
    assert store.books[1].available_copies == 3
    page = client.get("/ui/books").get_data(as_text=True)
    assert "Emma" in page and "Jane Austen" in page


def test_ui_delete_book_removes_it_from_page_and_store(client):
    make_book(client, title="Gone Soon")
    assert "Gone Soon" in client.get("/ui/books").get_data(as_text=True)

    client.post("/ui/books/1/delete")

    assert 1 not in store.books
    assert "Gone Soon" not in client.get("/ui/books").get_data(as_text=True)


def test_ui_checkout_then_return_updates_availability_and_page(client):
    make_book(client, total_copies=1)
    make_member(client)

    client.post("/ui/loans", data={"book_id": "1", "member_id": "1"})
    assert store.books[1].available_copies == 0
    loans_page = client.get("/ui/loans").get_data(as_text=True)
    assert "Return" in loans_page  # button offered for an open loan

    client.post("/ui/loans/1/return")
    assert store.books[1].available_copies == 1
    assert store.loans[1].return_date == date.today()
    assert 'action="/ui/loans/1/return"' not in client.get("/ui/loans").get_data(as_text=True)


def test_ui_checkout_of_unknown_book_records_no_loan(client):
    make_member(client)
    client.post("/ui/loans", data={"book_id": "99", "member_id": "1"})
    assert store.loans == {}


def test_ui_returning_a_loan_twice_does_not_add_extra_copies(client):
    make_book(client, total_copies=1)
    make_member(client)
    client.post("/ui/loans", data={"book_id": "1", "member_id": "1"})

    client.post("/ui/loans/1/return")
    client.post("/ui/loans/1/return")

    assert store.books[1].available_copies == 1


# ---------------------------------------------------------------------------
# Defect-exposing tests.  Each encodes the behaviour the requirement asks for;
# on the unmodified reference app they FAIL.  Explained in the report (Testing).
# ---------------------------------------------------------------------------
def test_checkout_is_refused_when_no_copies_are_available(client):
    """R13/R16: availability must stay accurate; a book with 0 copies left
    cannot be lent out.  Observed: 201 and available_copies becomes -1."""
    make_book(client, total_copies=1)
    make_member(client, "Ann", "a@x.com")
    make_member(client, "Bob", "b@x.com")
    client.post("/loans", json={"book_id": 1, "member_id": 1})

    resp = client.post("/loans", json={"book_id": 1, "member_id": 2})

    assert resp.status_code in (400, 409)
    assert client.get("/books/1").get_json()["available_copies"] == 0


def test_checkout_for_unknown_member_is_refused(client):
    """R16: each loan must record which (existing) member holds the book.
    Observed: 201 with member_id 99 although no such member exists."""
    make_book(client)

    resp = client.post("/loans", json={"book_id": 1, "member_id": 99})

    assert resp.status_code == 404
    assert client.get("/loans").get_json() == []


def test_loans_lookup_by_member_id_returns_only_that_members_loans(client):
    """R7: a member must be able to see their own loans.
    Observed: the filter compares loan.book_id with member_id."""
    make_book(client, "A", isbn="1")
    make_book(client, "B", isbn="2")
    make_member(client, "Ann", "a@x.com")
    make_member(client, "Bob", "b@x.com")
    client.post("/loans", json={"book_id": 1, "member_id": 2})  # Bob borrows book 1
    client.post("/loans", json={"book_id": 2, "member_id": 1})  # Ann borrows book 2

    result = client.get("/loans?member_id=1").get_json()

    assert [(l["member_id"], l["book_id"]) for l in result] == [(1, 2)]


def test_failed_checkout_leaves_available_copies_unchanged(lenient_client):
    """R13: a rejected checkout must not change availability.
    Observed: copies are decremented before member_id is read, so a request
    without member_id raises KeyError (500) AFTER removing a copy."""
    lenient_client.post(
        "/books", json={"title": "T", "author": "A", "isbn": "1", "total_copies": 2}
    )

    resp = lenient_client.post("/loans", json={"book_id": 1})  # member_id missing

    assert resp.status_code >= 400
    assert lenient_client.get("/books/1").get_json()["available_copies"] == 2
    assert lenient_client.get("/loans").get_json() == []


def test_ui_checkout_is_refused_when_no_copies_are_available(client):
    """R13: same rule through the web form.  Observed: available_copies -> -1."""
    make_book(client, total_copies=1)
    make_member(client)
    client.post("/ui/loans", data={"book_id": "1", "member_id": "1"})

    client.post("/ui/loans", data={"book_id": "1", "member_id": "1"})

    assert store.books[1].available_copies >= 0
    assert len(store.loans) == 1


# ---------------------------------------------------------------------------
# Enhancement (Yaseen): hold queue enforcement  (R8, R9)  - feature/hold-queue
#   * checkout respects the queue and stock       -> 409 when not allowed
#   * the borrowing holder's hold becomes fulfilled
#   * renew is refused while another member waits
#   * GET /reservations/queue?book_id=<id> shows the waiting order
# ---------------------------------------------------------------------------
def _single_copy_on_loan(client):
    """Book 1 (1 copy) on loan to Ann (id 1); Bob (2) and Cy (3) also exist."""
    make_book(client, total_copies=1)
    make_member(client, "Ann", "a@x.com")
    make_member(client, "Bob", "b@x.com")
    make_member(client, "Cy", "c@x.com")
    client.post("/loans", json={"book_id": 1, "member_id": 1})


def test_hold_queue_endpoint_lists_open_holds_in_order_with_positions(client):
    _single_copy_on_loan(client)
    client.post("/reservations", json={"book_id": 1, "member_id": 3})
    client.post("/reservations", json={"book_id": 1, "member_id": 2})

    resp = client.get("/reservations/queue?book_id=1")

    assert resp.status_code == 200
    queue = resp.get_json()
    assert [(q["position"], q["member_id"]) for q in queue] == [(1, 3), (2, 2)]
    assert [q["reservation_id"] for q in queue] == [1, 2]


def test_hold_queue_endpoint_validates_book_id(client):
    assert client.get("/reservations/queue").status_code == 400
    missing = client.get("/reservations/queue?book_id=99")
    assert missing.status_code == 404
    assert missing.get_json() == {"error": "Book not found"}


def test_second_in_queue_cannot_jump_ahead_and_fulfilled_hold_leaves_queue(client):
    _single_copy_on_loan(client)
    client.post("/reservations", json={"book_id": 1, "member_id": 2})  # Bob first
    client.post("/reservations", json={"book_id": 1, "member_id": 3})  # Cy second
    client.put("/loans/1/return")  # Ann returns; one copy is free

    cy_attempt = client.post("/loans", json={"book_id": 1, "member_id": 3})
    assert cy_attempt.status_code == 409
    assert cy_attempt.get_json() == {"error": "Book is on hold for another member"}
    assert client.get("/books/1").get_json()["available_copies"] == 1  # unchanged

    bob = client.post("/loans", json={"book_id": 1, "member_id": 2})
    assert bob.status_code == 201

    queue = client.get("/reservations/queue?book_id=1").get_json()
    assert [(q["position"], q["member_id"]) for q in queue] == [(1, 3)]  # Cy moved up
    assert client.get("/reservations?member_id=2").get_json()[0]["fulfilled"] is True


def test_checkout_with_no_free_copy_returns_409_and_keeps_count_at_zero(client):
    _single_copy_on_loan(client)

    resp = client.post("/loans", json={"book_id": 1, "member_id": 2})

    assert resp.status_code == 409
    assert resp.get_json() == {"error": "No copies available"}
    assert client.get("/books/1").get_json()["available_copies"] == 0


def test_spare_copies_beyond_the_holds_can_still_be_borrowed_by_anyone(client):
    make_book(client, total_copies=3)
    make_member(client, "Ann", "a@x.com")
    make_member(client, "Bob", "b@x.com")
    make_member(client, "Cy", "c@x.com")
    client.post("/loans", json={"book_id": 1, "member_id": 1})  # 2 copies left
    client.post("/reservations", json={"book_id": 1, "member_id": 2})  # 1 hold

    cy_first = client.post("/loans", json={"book_id": 1, "member_id": 3})  # 2 free > 1 hold
    assert cy_first.status_code == 201
    # 1 copy left and it is still reserved for Bob
    assert client.post("/loans", json={"book_id": 1, "member_id": 1}).status_code == 409
    assert client.post("/loans", json={"book_id": 1, "member_id": 2}).status_code == 201


def test_renew_is_blocked_while_a_hold_waits_and_allowed_once_none_wait(client):
    _single_copy_on_loan(client)
    client.post("/reservations", json={"book_id": 1, "member_id": 2})
    original_due = client.get("/loans").get_json()[0]["due_date"]

    blocked = client.put("/loans/1/renew")

    assert blocked.status_code == 409
    assert "hold" in blocked.get_json()["error"]
    assert client.get("/loans").get_json()[0]["due_date"] == original_due

    # Bob no longer waits (his hold is fulfilled after Ann returns and he borrows)
    client.put("/loans/1/return")
    client.post("/loans", json={"book_id": 1, "member_id": 2})
    assert client.put("/loans/2/renew").status_code == 200


def test_ui_checkout_respects_holds(client):
    _single_copy_on_loan(client)
    client.post("/reservations", json={"book_id": 1, "member_id": 2})
    client.put("/loans/1/return")

    client.post("/ui/loans", data={"book_id": "1", "member_id": "3"})  # Cy: not first
    assert len(store.loans) == 1 and store.books[1].available_copies == 1

    client.post("/ui/loans", data={"book_id": "1", "member_id": "2"})  # Bob: holder
    assert len(store.loans) == 2 and store.books[1].available_copies == 0
    assert store.reservations[1].fulfilled is True
