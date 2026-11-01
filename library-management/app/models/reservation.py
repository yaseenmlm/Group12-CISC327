from datetime import date


class Reservation:
    def __init__(self, id, book_id, member_id, reservation_date=None, fulfilled=False):
        self.id = id
        self.book_id = book_id
        self.member_id = member_id
        self.reservation_date = reservation_date or date.today()
        self.fulfilled = fulfilled

    def to_dict(self):
        return {
            "id": self.id,
            "book_id": self.book_id,
            "member_id": self.member_id,
            "reservation_date": self.reservation_date.isoformat(),
            "fulfilled": self.fulfilled,
        }


def active_holds(book_id):
    """Unfulfilled reservations for a book, oldest first (the hold queue)."""
    from app import store

    holds = [r for r in store.reservations.values() if r.book_id == book_id and not r.fulfilled]
    return sorted(holds, key=lambda r: r.id)


def can_check_out(book, member_id):
    """Whether ``member_id`` may take a copy of ``book`` right now.

    Copies are handed out in queue order: a member with a hold may borrow when
    their place is within the number of available copies; a member without a
    hold may borrow only if more copies are free than there are holds waiting.
    A book with no free copies can never be checked out.
    """
    holders = [h.member_id for h in active_holds(book.id)]
    if member_id in holders:
        return holders.index(member_id) < book.available_copies
    return book.available_copies > len(holders)


def fulfill_hold(book_id, member_id):
    """Mark the member's earliest open hold on the book as fulfilled."""
    for hold in active_holds(book_id):
        if hold.member_id == member_id:
            hold.fulfilled = True
            return hold
    return None
