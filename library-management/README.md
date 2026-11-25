# Library Management System (LMS)

A small Flask REST API for tracking books, members, and loans. Data is stored
**in memory** (plain Python objects, no database) and is reset every time the
app restarts — this project is meant to run before you've covered databases.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

The API runs at `http://127.0.0.1:5000`.

## Web UI

Open `http://127.0.0.1:5000/` in a browser for a basic HTML front end (plain
forms and tables, no JavaScript) to add/delete books and members, and check
books in/out:

| Page | Path |
|---|---|
| Home | `/` |
| Books | `/ui/books` |
| Members | `/ui/members` |
| Loans | `/ui/loans` |

This UI is separate from the JSON API below — it's there so you can see the
app working without a REST client, and calls the same in-memory store.

## Entities

- **Book**: `id, title, author, isbn, total_copies, available_copies`
- **Member**: `id, name, email, membership_date`
- **Loan**: `id, book_id, member_id, loan_date, due_date, return_date`
- **Reservation**: `id, book_id, member_id, reservation_date, fulfilled`

## JSON API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/books` | List all books |
| POST | `/books` | Create a book |
| GET | `/books/<id>` | Get one book |
| PUT | `/books/<id>` | Update a book |
| DELETE | `/books/<id>` | Delete a book |
| GET | `/members?search=` | List all members; `search` filters by name (case-insensitive, partial match) |
| POST | `/members` | Create a member |
| GET | `/members/<id>` | Get one member |
| PUT | `/members/<id>` | Update a member |
| DELETE | `/members/<id>` | Delete a member |
| GET | `/members/<id>/overdue` | Front-desk alert: `has_overdue` plus the member's open loans past their due date (`loan_id`, `book_id`, `book_title`, `due_date`, `days_overdue`) |
| POST | `/loans` | Check out a book (`book_id`, `member_id`) |
| PUT | `/loans/<id>/return` | Return a loaned book. The response also has `hold_notified`: `true` if the member next in the hold queue was sent a "hold ready" notification, `false` if the notification failed (the return still succeeds), `null` if nobody was waiting |
| GET | `/loans?member_id=&book_id=` | Look up loans |
| PUT | `/loans/<id>/renew` | Renew a loan for another 14 days (`409` if another member has a hold on the book) |
| GET | `/loans/<id>/fine` | Fine for a loan at $0.25 per day overdue |
| GET | `/reservations?book_id=&member_id=` | List reservations (holds) |
| POST | `/reservations` | Place a hold on a book (`book_id`, `member_id`) |
| GET | `/reservations/queue?book_id=` | Open holds for a book in the order they will be served (`position`, `reservation_id`, `member_id`, `reservation_date`) |

### Hold queue rules (checkout and renew)

- `POST /loans` returns `409` when no copy is free (`No copies available`) or when
  the free copies are reserved for members ahead of the borrower
  (`Book is on hold for another member`).
- When a member with a hold borrows the book, that hold is marked `fulfilled`
  and leaves the queue.
- `PUT /loans/<id>/renew` returns `409` while any other member has an open hold
  on the book.
- The same checkout rules apply to the web UI Loans page.

### Hold-ready notification

- When a loan is returned and the freed copy covers a member's place in the hold queue,
  the app calls `send_notification(member.email, subject, message)` from
  `notification_service.py` (a simulator beside `run.py`; no real email is sent).
- The member at position *n* of the queue is notified when *n* copies are free, so a
  return never notifies someone who is still behind the copies available.
- A failed notification never blocks the return: the loan is still returned and the
  response reports `"hold_notified": false`.
- The web UI return button follows the same rule.
- `POST /loans` now returns `404` (`Member not found`) for an unknown member, and
  `GET /loans?member_id=` now filters by the loan's member.

## Tests

Unit/integration tests (Flask test client, no server needed):

```bash
pytest --ignore=tests/e2e
```

## Running with Docker

**Prerequisites:** Docker Desktop (Windows/macOS) or Docker Engine (Linux).
Check with `docker --version`. Run these commands from the `library-management/`
folder (where the `Dockerfile` is).

| Step | Command |
|---|---|
| Build the image | `docker build -t cisc327-a4 .` |
| Run the container | `docker run --rm -p 5000:5000 --name cisc327-a4 cisc327-a4` |
| Open the app | <http://localhost:5000/> |
| Stop the container | `Ctrl+C` in its terminal, or `docker stop cisc327-a4` from another one |

- The app listens on **port 5000** inside the container (bound to `0.0.0.0`),
  and `-p 5000:5000` publishes it on port 5000 of your machine.
- `--rm` deletes the container when it stops.
- **Data does not persist.** Everything is kept in memory, so all books,
  members and loans are lost when the container stops — every `docker run`
  starts with an empty library. (Same as running `python run.py` locally.)
- Pre-built image on Docker Hub: `docker pull yaseenmlm/cisc327-a4:latest`
  then `docker run --rm -p 5000:5000 yaseenmlm/cisc327-a4:latest`.

## End-to-end (browser) tests

`tests/e2e/` uses [Playwright](https://playwright.dev/python/) to click through
the web UI in a real Chromium browser, over HTTP, against a **running** copy of
the app. Each test creates its own uniquely named books/members, so the tests
don't depend on each other or on what is already in memory.

| File | Member | Scenarios |
|---|---|---|
| `test_a4_yaseen.py` | Yaseen | check out + return a book; checkout blocked when no copies are left |
| `test_a4_rohan.py` | Rohan | add + delete a book; member with an invalid email is rejected |

One-time setup:

```bash
pip install -r requirements-e2e.txt
python -m playwright install chromium
```

Then start the app in one terminal — **either** locally **or** in Docker (both use port 5000, so only one at a time):

```bash
python run.py                                # local
docker run --rm -p 5000:5000 cisc327-a4      # or: container
```

and run the tests from a second terminal (in `library-management/`):

```bash
python -m pytest tests/e2e -v --headed       # --headed shows the browser
```

The tests target `http://127.0.0.1:5000` by default; set `E2E_BASE_URL` to point
them somewhere else. If nothing is running there, they stop with a message
telling you to start the app.
