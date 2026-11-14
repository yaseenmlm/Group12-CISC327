"""Notification simulator Assignment 3.

Place this file beside run.py in your selected project folder, then use
``import notification_service`` from application code.

This module does not send real emails or make network calls. Successful
notifications are stored in memory and disappear when Python exits. It is
a teaching simulator for a single process, not a production delivery system.
The application decides when to notify someone and how to handle failure.

Examples of recipients in the supplied templates:
    Library:          member.email
    Equipment rental: renter.email
    Inventory:        supplier.contact_email or a chosen staff address

For application tests, stub send_notification to return True or False, or
mock it to verify the recipient, subject, and message. Assert the resulting
application behavior too. Patch the dependency where your application uses it.
Use clear_notifications before and after tests that use the real simulator.

Group 12 customizations (Riverside Public Library, "hold available" event):
    * SUBJECT_PREFIX, HOLD_READY_SUBJECT and hold_ready_message() give the
      hold-ready notification a library sender tag and a message template.
    * send_notification() also returns False when the recipient does not
      contain "@" (the simulator's stand-in for an invalid email address).
    The function name, parameters and True/False return value are unchanged.
"""

SUBJECT_PREFIX = "[Riverside Library]"
HOLD_READY_SUBJECT = f"{SUBJECT_PREFIX} Your hold is ready for pickup"

_notifications = []


def hold_ready_message(member_name: str, book_title: str) -> str:
    """Return the body of the "your hold is ready" notification."""
    return (
        f"Hello {member_name}, a copy of \"{book_title}\" is now available for "
        "you at Riverside Public Library. Please pick it up at the front desk."
    )


def is_service_available() -> bool:
    """Return True for this local simulator.

    Tests may stub this function to return False to simulate an outage.
    No external service is contacted and no random failures are introduced.
    """
    return True


def send_notification(recipient: str, subject: str, message: str) -> bool:
    """Record a simulated notification and return True on success.

    Return False without recording anything if any argument is not a string,
    is empty/whitespace-only, the recipient is not an email-like address
    (no "@"), or the simulated service is unavailable.
    This simulator does not check deliverability.
    Valid values are stored exactly as supplied. Repeated sends are recorded
    separately. True means recorded by the simulator, not delivered by email.
    """
    if not all(isinstance(value, str) and value.strip()
               for value in (recipient, subject, message)):
        return False

    if "@" not in recipient:
        return False

    if not is_service_available():
        return False

    _notifications.append({
        "recipient": recipient,
        "subject": subject,
        "message": message,
    })
    return True


def get_notifications() -> list:
    """Return all recorded notifications in sending order.

    Return copies of the records so callers cannot modify the stored history.
    Each record has recipient, subject, and message string fields.
    """
    return [notification.copy() for notification in _notifications]


def clear_notifications() -> None:
    """Remove all recorded notifications, for example between test cases."""
    _notifications.clear()
