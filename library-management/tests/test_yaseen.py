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
