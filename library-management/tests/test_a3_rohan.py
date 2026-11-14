"""Assignment 3 tests written by Rohan (Member B).

Notification event: "hold available" (a returned copy is ready for the member
at the front of the hold queue).  These tests cover what Member A's file does
not: the notification failing, and the cases where no notification may be sent.

Test doubles
  * Stub  - send_notification patched to return False (state verification: the
            return still succeeds and the response says it was not sent).
  * Mock  - assert_not_called / assert_called_once on send_notification,
            always together with assertions on the response and the stored data.
  * Patched where the application uses it: app.routes.loans.send_notification.
  * Two tests use the real simulator and make it fail on its own (an address
    with no "@", and a stubbed outage via is_service_available).
"""
from datetime import date, timedelta
from unittest.mock import patch

import notification_service
from app import store


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


def checkout(client, book_id, member_id):
    resp = client.post("/loans", json={"book_id": book_id, "member_id": member_id})
    assert resp.status_code == 201
    return resp.get_json()


def hold(client, book_id, member_id):
    resp = client.post("/reservations", json={"book_id": book_id, "member_id": member_id})
    assert resp.status_code == 201
    return resp.get_json()


def waiting_scenario(client, bob_email="bob@example.com"):
    """Ann has the only copy of Dune; Bob is waiting for it."""
    make_book(client)
    make_member(client, "Ann", "ann@example.com")
    make_member(client, "Bob", bob_email)
    loan = checkout(client, 1, 1)
    hold(client, 1, 2)
    return loan


# ---------------------------------------------------------------------------
# Notification: failure paths
# ---------------------------------------------------------------------------
def test_return_still_succeeds_when_notification_stub_fails(client):
    """Stub: send_notification returns False -> return works, response says not sent."""
    loan = waiting_scenario(client)

    with patch("app.routes.loans.send_notification", return_value=False):  # stub
        resp = client.put(f"/loans/{loan['id']}/return")

    body = resp.get_json()
    assert resp.status_code == 200
    assert body["hold_notified"] is False
    assert body["return_date"] == date.today().isoformat()
    assert store.books[1].available_copies == 1
    assert store.reservations[1].fulfilled is False  # Bob can still borrow it


def test_failed_notification_is_attempted_once_for_the_right_member(client):
    """Mock returning False: one attempt for Bob, and the failure is reported."""
    loan = waiting_scenario(client)

    with patch("app.routes.loans.send_notification", return_value=False) as mock_send:
        resp = client.put(f"/loans/{loan['id']}/return")

    assert resp.status_code == 200
    assert resp.get_json()["hold_notified"] is False
    assert store.loans[loan["id"]].return_date is not None
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "bob@example.com"


def test_invalid_email_address_is_reported_as_not_notified(client):
    """Real simulator rejects an address with no "@": nothing recorded, return OK."""
    loan = waiting_scenario(client, bob_email="not-an-email")
    notification_service.clear_notifications()
    try:
        resp = client.put(f"/loans/{loan['id']}/return")
        recorded = notification_service.get_notifications()
    finally:
        notification_service.clear_notifications()

    assert resp.status_code == 200
    assert resp.get_json()["hold_notified"] is False
    assert recorded == []
    assert store.books[1].available_copies == 1


def test_service_outage_is_reported_as_not_notified(client):
    """Simulated outage (is_service_available -> False): return OK, nothing recorded."""
    loan = waiting_scenario(client)
    notification_service.clear_notifications()
    try:
        with patch("notification_service.is_service_available", return_value=False):
            resp = client.put(f"/loans/{loan['id']}/return")
        recorded = notification_service.get_notifications()
    finally:
        notification_service.clear_notifications()

    assert resp.status_code == 200
    assert resp.get_json()["hold_notified"] is False
    assert recorded == []
    assert store.loans[loan["id"]].return_date is not None


# ---------------------------------------------------------------------------
# Notification: no notification when the conditions are not met
# ---------------------------------------------------------------------------
def test_no_notification_when_nobody_is_waiting(client):
    make_book(client)
    make_member(client)
    loan = checkout(client, 1, 1)

    with patch("app.routes.loans.send_notification") as mock_send:
        resp = client.put(f"/loans/{loan['id']}/return")

    assert resp.status_code == 200
    assert resp.get_json()["hold_notified"] is None
    assert store.books[1].available_copies == 1
    mock_send.assert_not_called()


def test_no_notification_once_the_hold_has_been_fulfilled(client):
    """Bob was told, borrowed the book (hold fulfilled); his own return tells nobody."""
    loan = waiting_scenario(client)
    client.put(f"/loans/{loan['id']}/return")
    bob_loan = checkout(client, 1, 2)
    assert store.reservations[1].fulfilled is True

    with patch("app.routes.loans.send_notification") as mock_send:
        resp = client.put(f"/loans/{bob_loan['id']}/return")

    assert resp.status_code == 200
    assert resp.get_json()["hold_notified"] is None
    mock_send.assert_not_called()


def test_hold_on_another_book_does_not_trigger_a_notification(client):
    make_book(client, "Dune", isbn="1")
    make_book(client, "Emma", "Jane Austen", isbn="2")
    make_member(client, "Ann", "ann@example.com")
    make_member(client, "Bob", "bob@example.com")
    dune_loan = checkout(client, 1, 1)
    checkout(client, 2, 1)
    hold(client, 2, 2)  # Bob waits for Emma, not Dune

    with patch("app.routes.loans.send_notification") as mock_send:
        resp = client.put(f"/loans/{dune_loan['id']}/return")

    assert resp.status_code == 200
    assert resp.get_json()["hold_notified"] is None
    assert store.books[1].available_copies == 1
    mock_send.assert_not_called()


def test_second_returned_copy_does_not_renotify_a_single_waiting_member(client):
    """Two copies out, one member waiting: only the first return notifies Bob."""
    make_book(client, total_copies=2)
    make_member(client, "Ann", "ann@example.com")
    make_member(client, "Di", "di@example.com")
    make_member(client, "Bob", "bob@example.com")
    first = checkout(client, 1, 1)
    second = checkout(client, 1, 2)
    hold(client, 1, 3)

    with patch("app.routes.loans.send_notification", return_value=True) as mock_send:
        r1 = client.put(f"/loans/{first['id']}/return")
        r2 = client.put(f"/loans/{second['id']}/return")

    assert r1.get_json()["hold_notified"] is True
    assert r2.status_code == 200
    assert r2.get_json()["hold_notified"] is None
    assert store.books[1].available_copies == 2
    mock_send.assert_called_once()


def test_already_returned_loan_sends_nothing_and_changes_nothing(client):
    loan = waiting_scenario(client)
    client.put(f"/loans/{loan['id']}/return")  # first return (notification sent)

    with patch("app.routes.loans.send_notification") as mock_send:
        resp = client.put(f"/loans/{loan['id']}/return")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Loan already returned"}
    assert store.books[1].available_copies == 1
    mock_send.assert_not_called()


def test_unknown_loan_sends_nothing(client):
    with patch("app.routes.loans.send_notification") as mock_send:
        resp = client.put("/loans/99/return")

    assert resp.status_code == 404
    mock_send.assert_not_called()


def test_web_ui_return_with_nobody_waiting_sends_nothing(client):
    make_book(client)
    make_member(client)
    checkout(client, 1, 1)

    with patch("app.routes.loans.send_notification") as mock_send:
        resp = client.post("/ui/loans/1/return")

    assert resp.status_code == 302
    assert store.loans[1].return_date is not None
    assert store.books[1].available_copies == 1
    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Coverage-directed tests: holds (R8) and fines on returned loans
# ---------------------------------------------------------------------------
def test_same_member_cannot_hold_the_same_book_twice_and_keeps_one_hold(client):
    waiting_scenario(client)

    resp = client.post("/reservations", json={"book_id": 1, "member_id": 2})

    assert resp.status_code == 409
    assert resp.get_json() == {"error": "Member already has a hold on this book"}
    assert [r.member_id for r in store.reservations.values()] == [2]


def test_different_members_can_hold_the_same_book_in_order(client):
    waiting_scenario(client)
    make_member(client, "Cy", "cy@example.com")

    resp = client.post("/reservations", json={"book_id": 1, "member_id": 3})
    queue = client.get("/reservations/queue?book_id=1").get_json()

    assert resp.status_code == 201
    assert [(q["position"], q["member_id"]) for q in queue] == [(1, 2), (2, 3)]


def test_member_can_hold_two_different_books(client):
    make_book(client, "Dune", isbn="1")
    make_book(client, "Emma", "Jane Austen", isbn="2")
    make_member(client, "Ann", "ann@example.com")
    make_member(client, "Bob", "bob@example.com")
    checkout(client, 1, 1)
    checkout(client, 2, 1)
    hold(client, 1, 2)

    resp = client.post("/reservations", json={"book_id": 2, "member_id": 2})

    assert resp.status_code == 201
    assert sorted((r.book_id, r.member_id) for r in store.reservations.values()) == [(1, 2), (2, 2)]


def test_member_can_hold_again_after_their_earlier_hold_was_fulfilled(client):
    loan = waiting_scenario(client)
    client.put(f"/loans/{loan['id']}/return")
    checkout(client, 1, 2)  # Bob borrows, his hold is fulfilled
    assert store.reservations[1].fulfilled is True

    resp = client.post("/reservations", json={"book_id": 1, "member_id": 2})

    assert resp.status_code == 201
    assert [r.fulfilled for r in store.reservations.values()] == [True, False]


def _returned_loan(client, due_days_ago, returned_days_ago):
    make_book(client)
    make_member(client)
    loan = checkout(client, 1, 1)
    client.put(f"/loans/{loan['id']}/return")
    stored = store.loans[loan["id"]]
    stored.due_date = date.today() - timedelta(days=due_days_ago)
    stored.return_date = date.today() - timedelta(days=returned_days_ago)
    return loan["id"]


def test_fine_of_a_returned_loan_is_fixed_at_the_return_date(client):
    """Due 10 days ago, returned 5 days ago -> 5 days late = 1.25, not 10 days."""
    loan_id = _returned_loan(client, due_days_ago=10, returned_days_ago=5)

    resp = client.get(f"/loans/{loan_id}/fine")

    assert resp.status_code == 200
    assert resp.get_json() == {"loan_id": loan_id, "fine_amount": 1.25}


def test_loan_returned_before_the_due_date_has_no_fine(client):
    loan_id = _returned_loan(client, due_days_ago=-3, returned_days_ago=1)

    assert client.get(f"/loans/{loan_id}/fine").get_json()["fine_amount"] == 0.0


def test_loan_returned_on_the_due_date_has_no_fine(client):
    loan_id = _returned_loan(client, due_days_ago=4, returned_days_ago=4)

    assert client.get(f"/loans/{loan_id}/fine").get_json()["fine_amount"] == 0.0


def test_fine_of_an_unreturned_overdue_loan_still_counts_up_to_today(client):
    make_book(client)
    make_member(client)
    loan = checkout(client, 1, 1)
    store.loans[loan["id"]].due_date = date.today() - timedelta(days=3)

    resp = client.get(f"/loans/{loan['id']}/fine")

    assert resp.get_json()["fine_amount"] == 0.75
    assert store.loans[loan["id"]].return_date is None
