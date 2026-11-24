"""Shared setup for the browser-based end-to-end tests.

These tests drive a real browser against a *running* copy of the app over
HTTP: either `python run.py` on your machine or the Docker container. They
never import the Flask app or use test_client().

Base URL defaults to http://127.0.0.1:5000. Override it with the
E2E_BASE_URL environment variable if the app runs somewhere else.
"""
import os
import urllib.error
import urllib.request
import uuid

import pytest

DEFAULT_BASE_URL = "http://127.0.0.1:5000"


@pytest.fixture(scope="session")
def base_url():
    """Overrides pytest-base-url so page.goto("/ui/books") hits the running app."""
    return os.environ.get("E2E_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


@pytest.fixture(scope="session", autouse=True)
def _app_is_running(base_url):
    """Fail fast with a clear message if nothing is listening on the base URL."""
    try:
        urllib.request.urlopen(base_url + "/", timeout=5)
    except (urllib.error.URLError, OSError) as exc:
        pytest.fail(
            f"Cannot reach the app at {base_url} ({exc}). Start it first with "
            "`python run.py` or `docker run --rm -p 5000:5000 cisc327-a4`.",
            pytrace=False,
        )


@pytest.fixture
def unique():
    """Short random tag so each test creates its own data.

    The app keeps everything in memory and the server is not restarted between
    tests, so tests must never rely on fixed IDs or on data another test made.
    """
    return uuid.uuid4().hex[:8]
