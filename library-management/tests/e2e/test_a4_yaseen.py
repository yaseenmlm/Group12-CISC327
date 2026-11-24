"""A4 end-to-end tests - Member A (Yaseen): loan workflows on the Loans page.

Scenario A1 (success):  check out a book, then return it, and confirm the
                        loan record and the book's available copies update.
Scenario A2 (boundary): try to check out a book whose only copy is already on
                        loan, and confirm no second loan is created.

Each test creates its own book and member(s) with a unique tag, so the tests
pass in any order against a fresh or a long-running server.
"""
import re
from datetime import date, timedelta

from playwright.sync_api import Page, expect

LOAN_PERIOD_DAYS = 14


# ---------- helpers: plain user actions through the web UI ----------

def add_book(page: Page, title: str, copies: int) -> str:
    """Fill the Add a Book form and return the new book's ID from the table."""
    page.goto("/ui/books")
    page.get_by_label("Title").fill(title)
    page.get_by_label("Author").fill("E2E Author")
    page.get_by_label("ISBN").fill("978-0000000000")
    page.get_by_label("Total Copies").fill(str(copies))
    page.get_by_role("button", name="Add Book").click()

    row = page.get_by_role("row").filter(has_text=title)
    expect(row).to_have_count(1)
    return row.get_by_role("cell").nth(0).inner_text().strip()


def add_member(page: Page, name: str) -> str:
    """Fill the Add a Member form and return the new member's ID."""
    page.goto("/ui/members")
    page.get_by_label("Name").fill(name)
    page.get_by_label("Email").fill(f"{name.replace(' ', '.').lower()}@example.com")
    page.get_by_role("button", name="Add Member").click()

    row = page.get_by_role("row").filter(has_text=name)
    expect(row).to_have_count(1)
    return row.get_by_role("cell").nth(0).inner_text().strip()


def check_out(page: Page, book_id: str, member_id: str) -> None:
    page.goto("/ui/loans")
    page.get_by_label("Book ID").fill(book_id)
    page.get_by_label("Member ID").fill(member_id)
    page.get_by_role("button", name="Check Out").click()
    expect(page).to_have_url(re.compile(r"/ui/loans$"))


def loan_rows(page: Page, book_id: str, member_id: str | None = None):
    """Rows on the Loans table for this book (and optionally this member).

    Columns: ID | Book ID | Member ID | Loan Date | Due Date | Return Date | action
    """
    rows = page.get_by_role("row").filter(
        has=page.locator("td:nth-child(2)", has_text=re.compile(rf"^{book_id}$"))
    )
    if member_id is not None:
        rows = rows.filter(
            has=page.locator("td:nth-child(3)", has_text=re.compile(rf"^{member_id}$"))
        )
    return rows


def available_copies(page: Page, title: str) -> str:
    """Read the Available column (6th) for a book on the Books page."""
    page.goto("/ui/books")
    row = page.get_by_role("row").filter(has_text=title)
    return row.get_by_role("cell").nth(5).inner_text().strip()


# ---------- tests ----------

def test_checkout_then_return_updates_loan_and_availability(page: Page, unique: str):
    """A1 - success: a member borrows a book and brings it back."""
    title = f"E2E Loan Book {unique}"
    book_id = add_book(page, title, copies=2)
    member_id = add_member(page, f"Loan Member {unique}")

    # Check out -> a new open loan appears with a 14-day due date
    check_out(page, book_id, member_id)
    row = loan_rows(page, book_id, member_id)
    expect(row).to_have_count(1)
    cells = row.get_by_role("cell")
    today = date.today()
    expect(cells.nth(3)).to_have_text(today.isoformat())                       # Loan Date
    expect(cells.nth(4)).to_have_text((today + timedelta(days=LOAN_PERIOD_DAYS)).isoformat())
    expect(cells.nth(5)).to_have_text("-")                                     # not returned
    expect(row.get_by_role("button", name="Return")).to_be_visible()

    # One of the two copies is now out
    assert available_copies(page, title) == "1"

    # Return it -> return date is set and the Return button disappears
    page.goto("/ui/loans")
    loan_rows(page, book_id, member_id).get_by_role("button", name="Return").click()
    row = loan_rows(page, book_id, member_id)
    expect(row.get_by_role("cell").nth(5)).to_have_text(today.isoformat())
    expect(row.get_by_role("button", name="Return")).to_have_count(0)

    # Both copies are back on the shelf
    assert available_copies(page, title) == "2"


def test_checkout_rejected_when_no_copies_available(page: Page, unique: str):
    """A2 - boundary: available copies is 0, so a second checkout must not go through."""
    title = f"E2E Single Copy {unique}"
    book_id = add_book(page, title, copies=1)
    first_member = add_member(page, f"First Borrower {unique}")
    second_member = add_member(page, f"Second Borrower {unique}")

    # The only copy goes to the first member (availability 1 -> 0)
    check_out(page, book_id, first_member)
    expect(loan_rows(page, book_id, first_member)).to_have_count(1)
    assert available_copies(page, title) == "0"

    # Second member tries to borrow the same book
    check_out(page, book_id, second_member)

    # No loan was created for the second member, and the book still has exactly one loan
    expect(loan_rows(page, book_id, second_member)).to_have_count(0)
    expect(loan_rows(page, book_id)).to_have_count(1)
    # Availability did not go negative
    assert available_copies(page, title) == "0"
