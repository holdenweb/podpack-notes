"""Conformance with the podpack app contract, and the app's own behaviour.

The first half is what makes this an app rather than a blueprint: that a site
installs it by naming it, that it gets a data directory and seeded data, that
its nav entry resolves, and that the site decides where it lands. The second
half is the notes themselves.
"""

from typing import Any

import pytest
from flask import Flask

from conftest import SiteFactory

from podpack_notes import site_app


def test_the_app_names_itself_after_its_blueprint() -> None:
    """Three spellings of one thing, and only this one keys the config.

    The distribution is `podpack-notes` and the import name `podpack_notes`, but
    podpack resolves an app from its blueprint at runtime -- so `notes` is what
    `[apps.notes]`, `[site.mounts]` and the directories on disk are keyed by.
    """
    assert site_app.name == site_app.blueprint.name == "notes"


def test_a_site_installs_it_by_naming_it(site: SiteFactory) -> None:
    """The whole point of the framework: a line of config, not a line of code."""
    app = site()
    assert app.test_client().get("/notes/").status_code == 200
    assert app.extensions["podpack"].installed_from == {"notes": "podpack_notes"}


def test_it_wears_the_sites_chrome(app: Flask) -> None:
    """The app extends `base.html` without knowing whose it is."""
    body = app.test_client().get("/notes/").get_data(as_text=True)
    assert "<h2>Notes</h2>" in body
    assert "Served by podpack" in body  # the default chrome, since this site ships none


def test_its_nav_entry_reaches_the_site(app: Flask) -> None:
    assert [s.label for s in app.extensions["podpack"].nav] == ["Notes"]
    assert 'href="/notes/"' in app.test_client().get("/").get_data(as_text=True)


def test_the_site_decides_where_it_lands(site: SiteFactory) -> None:
    """`url_prefix` is what this app asks for, not what it is entitled to."""
    app = site(
        host_config={
            "site": {
                "name": "test site",
                "environment": "test",
                "apps": ["podpack_notes"],
                "mounts": {"notes": "/writing/notes"},
            }
        }
    )
    client = app.test_client()
    assert client.get("/writing/notes/").status_code == 200
    assert client.get("/notes/").status_code == 404
    # The nav follows with neither side restating anything.
    assert 'href="/writing/notes/"' in client.get("/").get_data(as_text=True)


def test_its_shipped_data_is_seeded_to_the_host(app: Flask) -> None:
    """`welcome.md` travels with the package and is copied out on install."""
    welcome = app.extensions["podpack"].data_root / "notes" / "welcome.md"
    assert welcome.is_file()
    assert "ships inside the notes app" in welcome.read_text()


def test_it_reads_the_host_copy_not_the_packaged_one(app: Flask) -> None:
    """Which is what makes seeded data editable without a rebuild."""
    welcome = app.extensions["podpack"].data_root / "notes" / "welcome.md"
    welcome.write_text("edited on the host")
    assert "edited on the host" in app.test_client().get("/notes/").get_data(as_text=True)


def test_its_page_size_comes_from_the_site(site: SiteFactory) -> None:
    """`[apps.notes] page_size` is this app's own namespace, and nothing else's."""
    app = site()
    client = app.test_client()
    for n in range(7):
        client.post("/notes/", json={"text": f"note {n}"})
    # The fixture site sets page_size = 5.
    assert len(client.get("/notes/list").get_json()["notes"]) == 5


def test_a_site_without_the_setting_gets_the_packaged_default(site: SiteFactory) -> None:
    app = site(host_config={"apps": {}})
    with app.test_request_context("/notes/"):
        from podpack_notes.views import _recent

        assert _recent() == []  # no rows, but the default did not raise


def test_notes_round_trip(app: Flask) -> None:
    client = app.test_client()
    assert client.post("/notes/", json={"text": "hello"}).status_code == 201
    assert "hello" in client.get("/notes/").get_data(as_text=True)
    assert client.get("/notes/list").get_json()["notes"][0]["text"] == "hello"


def test_an_empty_note_is_refused(app: Flask) -> None:
    response = app.test_client().post("/notes/", json={"text": "   "})
    assert response.status_code == 400


def test_uploads_land_in_the_apps_own_directory(app: Flask) -> None:
    """The app never builds that path itself; `data_dir()` resolves it."""
    response = app.test_client().post("/notes/uploads/probe.txt", data=b"hello")
    assert response.status_code == 201
    stored = app.extensions["podpack"].data_root / "notes" / "probe.txt"
    assert stored.read_bytes() == b"hello"


def test_an_upload_cannot_escape_that_directory(app: Flask) -> None:
    """`pathlib.Path(name).name` is what stops a traversal reaching the root."""
    app.test_client().post("/notes/uploads/..%2Fescaped.txt", data=b"x")
    root = app.extensions["podpack"].data_root
    assert not (root / "escaped.txt").exists()
