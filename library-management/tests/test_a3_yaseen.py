"""Assignment 3 tests written by Yaseen (Member A).

Notification event: "hold available".  When a loan is returned and a copy
becomes free for the member waiting at the front of the hold queue, the
application calls send_notification(member.email, subject, message).

Test doubles
  * Stub  - patch send_notification with a fixed return value and check the
            application's response and state (state verification).
  * Mock  - patch send_notification and assert how it was called (behaviour
            verification).  Every mock test also asserts the HTTP response and
            the loan/book/hold state.
  * The dependency is patched where the application uses it:
            app.routes.loans.send_notification (the UI return route reuses the
            same helper, so the same name is patched for it).

Member B's tests cover failure (stub False) and "no notification" paths.
"""
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


def waiting_scenario(client):
    """Ann has the only copy of Dune; Bob is waiting for it."""
    make_book(client)
    make_member(client, "Ann", "ann@example.com")
    make_member(client, "Bob", "bob@example.com")
    loan = checkout(client, 1, 1)
    hold(client, 1, 2)
    return loan


# ---------------------------------------------------------------------------
# Notification: success path (stub True and mocks)
# ---------------------------------------------------------------------------
def test_return_with_stub_true_reports_hold_notified(client):
    """Stub: send_notification always succeeds -> response says notified."""
    loan = waiting_scenario(client)

    with patch("app.routes.loans.send_notification", return_value=True):  # stub
        resp = client.put(f"/loans/{loan['id']}/return")

    body = resp.get_json()
    assert resp.status_code == 200
    assert body["hold_notified"] is True
    assert body["return_date"] is not None
    assert store.books[1].available_copies == 1
    # being told is not the same as borrowing: Bob's hold stays open
    assert store.reservations[1].fulfilled is False


def test_return_sends_hold_ready_notification_to_first_in_queue(client):
    """Mock: one call, with Bob's email, the library subject and a message for Bob."""
    loan = waiting_scenario(client)

    with patch("app.routes.loans.send_notification", return_value=True) as mock_send:
        resp = client.put(f"/loans/{loan['id']}/return")

    assert resp.status_code == 200
    assert resp.get_json()["hold_notified"] is True
    assert store.loans[loan["id"]].return_date is not None
    mock_send.assert_called_once_with(
        "bob@example.com",
        "[Riverside Library] Your hold is ready for pickup",
        'Hello Bob, a copy of "Dune" is now available for you at Riverside Public Library. '
        "Please pick it up at the front desk.",
    )


def test_only_the_front_of_the_queue_is_notified(client):
    """Mock: with two members waiting for one copy, only the first is told."""
    loan = waiting_scenario(client)
    make_member(client, "Cy", "cy@example.com")
    hold(client, 1, 3)

    with patch("app.routes.loans.send_notification", return_value=True) as mock_send:
        resp = client.put(f"/loans/{loan['id']}/return")

    assert resp.status_code == 200
    assert resp.get_json()["hold_notified"] is True
    assert mock_send.call_count == 1
    assert mock_send.call_args.args[0] == "bob@example.com"
    # both holds are still open and keep their order
    assert [h.member_id for h in store.reservations.values() if not h.fulfilled] == [2, 3]


def test_each_returned_copy_notifies_the_next_member_in_line(client):
    """Mock: two copies out, two members waiting -> Bob after the first return,
    Cy after the second."""
    make_book(client, total_copies=2)
    for name, email in [("Ann", "ann@example.com"), ("Di", "di@example.com"),
                        ("Bob", "bob@example.com"), ("Cy", "cy@example.com")]:
        make_member(client, name, email)
    first = checkout(client, 1, 1)
    second = checkout(client, 1, 2)
    hold(client, 1, 3)  # Bob
    hold(client, 1, 4)  # Cy

    with patch("app.routes.loans.send_notification", return_value=True) as mock_send:
        r1 = client.put(f"/loans/{first['id']}/return")
        r2 = client.put(f"/loans/{second['id']}/return")

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.get_json()["hold_notified"] is True
    assert r2.get_json()["hold_notified"] is True
    assert [call.args[0] for call in mock_send.call_args_list] == [
        "bob@example.com",
        "cy@example.com",
    ]
    assert store.books[1].available_copies == 2


def test_web_ui_return_also_sends_hold_ready_notification(client):
    """Mock: returning through the Loans page notifies the waiting member too."""
    waiting_scenario(client)

    with patch("app.routes.loans.send_notification", return_value=True) as mock_send:
        resp = client.post("/ui/loans/1/return")

    assert resp.status_code == 302  # redirect back to the loans page
    assert store.loans[1].return_date is not None
    assert store.books[1].available_copies == 1
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "bob@example.com"


def test_real_simulator_records_hold_ready_notification(client):
    """No test double: the simulator stores exactly what the app sent."""
    loan = waiting_scenario(client)
    notification_service.clear_notifications()
    try:
        resp = client.put(f"/loans/{loan['id']}/return")
        recorded = notification_service.get_notifications()
    finally:
        notification_service.clear_notifications()

    assert resp.status_code == 200
    assert resp.get_json()["hold_notified"] is True
    assert recorded == [{
        "recipient": "bob@example.com",
        "subject": "[Riverside Library] Your hold is ready for pickup",
        "message": 'Hello Bob, a copy of "Dune" is now available for you at '
                   "Riverside Public Library. Please pick it up at the front desk.",
    }]


def test_hold_ready_message_names_the_member_and_the_book():
    """The customized template used for the notification body."""
    message = notification_service.hold_ready_message("Bob", "Dune")

    assert "Bob" in message and '"Dune"' in message
    assert notification_service.HOLD_READY_SUBJECT.startswith("[Riverside Library]")


def test_deleted_member_with_a_hold_is_not_notified(client):
    """Mock: the waiting member was deleted -> nothing to send, return still works."""
    loan = waiting_scenario(client)
    assert client.delete("/members/2").status_code == 204

    with patch("app.routes.loans.send_notification") as mock_send:
        resp = client.put(f"/loans/{loan['id']}/return")

    assert resp.status_code == 200
    assert resp.get_json()["hold_notified"] is False
    assert store.books[1].available_copies == 1
    mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# Coverage-directed tests: loans lookup (R7) and checkout validation (R16)
# ---------------------------------------------------------------------------
def test_loans_lookup_combines_member_and_book_filters(client):
    make_book(client, "A", isbn="1", total_copies=2)
    make_book(client, "B", isbn="2")
    make_member(client, "Ann", "ann@example.com")
    make_member(client, "Bob", "bob@example.com")
    checkout(client, 1, 1)  # Ann, book 1
    checkout(client, 1, 2)  # Bob, book 1
    checkout(client, 2, 1)  # Ann, book 2

    result = client.get("/loans?member_id=1&book_id=1").get_json()

    assert [(l["member_id"], l["book_id"]) for l in result] == [(1, 1)]


def test_loans_lookup_for_member_without_loans_is_empty(client):
    make_book(client)
    make_member(client, "Ann", "ann@example.com")
    make_member(client, "Bob", "bob@example.com")
    checkout(client, 1, 1)

    resp = client.get("/loans?member_id=2")

    assert resp.status_code == 200
    assert resp.get_json() == []


def test_loans_lookup_keeps_returned_loans_in_a_members_history(client):
    make_book(client)
    make_member(client, "Ann", "ann@example.com")
    loan = checkout(client, 1, 1)
    client.put(f"/loans/{loan['id']}/return")

    result = client.get("/loans?member_id=1").get_json()

    assert [l["id"] for l in result] == [loan["id"]]
    assert result[0]["return_date"] is not None


def test_checkout_for_unknown_member_is_rejected_without_side_effects(client):
    make_book(client, total_copies=2)

    resp = client.post("/loans", json={"book_id": 1, "member_id": 99})

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Member not found"}
    assert store.loans == {}
    assert store.books[1].available_copies == 2


def test_checkout_for_unknown_book_is_rejected_before_member_check(client):
    make_member(client)

    resp = client.post("/loans", json={"book_id": 42, "member_id": 1})

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Book not found"}
    assert store.loans == {}


def test_last_copy_checkout_then_next_member_is_refused(client):
    """Boundary: taking the last copy leaves 0 free, the next checkout gets 409."""
    make_book(client)
    make_member(client, "Ann", "ann@example.com")
    make_member(client, "Bob", "bob@example.com")
    checkout(client, 1, 1)
    assert store.books[1].available_copies == 0

    resp = client.post("/loans", json={"book_id": 1, "member_id": 2})

    assert resp.status_code == 409
    assert resp.get_json() == {"error": "No copies available"}
    assert store.books[1].available_copies == 0
    assert len(store.loans) == 1
