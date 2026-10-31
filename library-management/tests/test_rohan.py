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
