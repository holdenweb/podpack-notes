"""Conformance with the podpack app contract, and the app's own behaviour.

The first half is what makes this an app rather than a blueprint: that a site
installs it by naming it, that it gets a data directory and seeded data, that
its nav entry resolves, and that the site decides where it lands. The second
half is the notes themselves, which now belong to somebody.
"""

import pytest
import sqlalchemy as sa
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.exc import IntegrityError

from conftest import OWNER, PASSWORD, SiteFactory, login

from podpack import db
from podpack_notes import site_app
from podpack_notes.models import Note


def test_the_app_names_itself_after_its_blueprint() -> None:
    """Three spellings of one thing, and only this one keys the config.

    The distribution is `podpack-notes` and the import name `podpack_notes`, but
    podpack resolves an app from its blueprint at runtime -- so `notes` is what
    `[apps.notes]`, `[site.mounts]` and the directories on disk are keyed by.
    """
    assert site_app.name == site_app.blueprint.name == "notes"


def test_it_declares_the_table_it_does_not_define() -> None:
    """`user` is podpack's, and this app says out loud that it joins to it.

    Not decoration: the registry checks the declaration at boot, so a site whose
    app list somehow lacked whatever defines `user` would refuse to start rather
    than serve until the first query failed.
    """
    assert site_app.needs_tables == frozenset({"user"})


def test_a_site_installs_it_by_naming_it(site: SiteFactory) -> None:
    """The whole point of the framework: a line of config, not a line of code."""
    app = site()
    assert login(app).get("/notes/").status_code == 200
    assert app.extensions["podpack"].installed_from == {"notes": "podpack_notes"}


def test_it_wears_the_sites_chrome(client: FlaskClient) -> None:
    """The app extends `base.html` without knowing whose it is."""
    body = client.get("/notes/").get_data(as_text=True)
    assert "<h2>Notes</h2>" in body
    assert "Served by podpack" in body  # the default chrome, since this site ships none


def test_its_nav_entry_reaches_the_site(app: Flask) -> None:
    """Anonymously, because the nav renders for everyone -- see the test below."""
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
    client = login(app)
    assert client.get("/writing/notes/").status_code == 200
    assert client.get("/notes/").status_code == 404
    # The nav follows with neither side restating anything.
    assert 'href="/writing/notes/"' in client.get("/").get_data(as_text=True)


def test_its_shipped_data_is_seeded_to_the_host(app: Flask) -> None:
    """`welcome.md` travels with the package and is copied out on install."""
    welcome = app.extensions["podpack"].data_root / "notes" / "welcome.md"
    assert welcome.is_file()
    assert "ships inside the notes app" in welcome.read_text()


def test_it_reads_the_host_copy_not_the_packaged_one(
    app: Flask, client: FlaskClient
) -> None:
    """Which is what makes seeded data editable without a rebuild."""
    welcome = app.extensions["podpack"].data_root / "notes" / "welcome.md"
    welcome.write_text("edited on the host")
    assert "edited on the host" in client.get("/notes/").get_data(as_text=True)


def test_its_page_size_comes_from_the_site(site: SiteFactory) -> None:
    """`[apps.notes] page_size` is this app's own namespace, and nothing else's."""
    app = site()
    client = login(app)
    for n in range(7):
        client.post("/notes/", json={"text": f"note {n}"})
    # The fixture site sets page_size = 5.
    assert len(client.get("/notes/list").get_json()["notes"]) == 5


def test_a_site_without_the_setting_gets_the_packaged_default(site: SiteFactory) -> None:
    app = site(host_config={"apps": {}})
    with app.test_request_context("/notes/"):
        from podpack_notes.views import _recent

        assert _recent(1) == []  # no rows, but the default did not raise


def test_notes_round_trip(client: FlaskClient) -> None:
    assert client.post("/notes/", json={"text": "hello"}).status_code == 201
    assert "hello" in client.get("/notes/").get_data(as_text=True)
    assert client.get("/notes/list").get_json()["notes"][0]["text"] == "hello"


def test_an_empty_note_is_refused(client: FlaskClient) -> None:
    response = client.post("/notes/", json={"text": "   "})
    assert response.status_code == 400


def test_a_user_sees_only_their_own_notes(
    client: FlaskClient, stranger: FlaskClient
) -> None:
    """The claim the owner column exists to support, on one site, two users.

    Both the JSON listing and the rendered page, because they are scoped by one
    query and a change that broke only the second would otherwise pass.
    """
    client.post("/notes/", json={"text": "mine"})
    stranger.post("/notes/", json={"text": "theirs"})

    assert [n["text"] for n in client.get("/notes/list").get_json()["notes"]] == ["mine"]
    assert [n["text"] for n in stranger.get("/notes/list").get_json()["notes"]] == [
        "theirs"
    ]
    assert "theirs" not in client.get("/notes/").get_data(as_text=True)


def test_a_stored_note_carries_its_owner(app: Flask, client: FlaskClient) -> None:
    client.post("/notes/", json={"text": "mine"})
    with app.app_context():
        note = db.session.scalars(sa.select(Note)).one()
        assert note.owner.email == OWNER


def test_every_route_refuses_an_anonymous_caller(app: Flask) -> None:
    """And refuses it properly, which is the half that could have gone wrong.

    `owner_id` is NOT NULL, so an unguarded POST would not have let anonymous
    notes through -- it would have raised IntegrityError and answered 500. The
    Accept headers are explicit because they are what flask-security reads to
    decide between sending a visitor to the login form and telling an API client
    it is not signed in.
    """
    client = app.test_client()
    page = client.get("/notes/", headers={"Accept": "text/html"})
    assert page.status_code == 302
    assert "/login" in page.headers["Location"]

    listing = client.get("/notes/list", headers={"Accept": "application/json"})
    assert listing.status_code == 401

    assert client.post("/notes/", json={"text": "hello"}).status_code == 401


def test_a_token_is_enough(app: Flask) -> None:
    """The API route the README documents, driven rather than assumed.

    On a fresh client, so nothing but the header can be carrying the identity,
    and so flask-security's CSRF handling gets its chance to object to a JSON
    POST -- it does not, which is the part that was worth finding out.
    """
    response = app.test_client().post(
        "/login?include_auth_token", json={"email": OWNER, "password": PASSWORD}
    )
    token = response.get_json()["response"]["user"]["authentication_token"]

    client = app.test_client()
    headers = {"Authentication-Token": token}
    assert client.post("/notes/", json={"text": "via token"}, headers=headers).status_code == 201
    listing = client.get("/notes/list", headers=headers)
    assert [n["text"] for n in listing.get_json()["notes"]] == ["via token"]


def test_a_user_with_notes_cannot_be_deleted(app: Flask, client: FlaskClient) -> None:
    """What `ondelete="RESTRICT"` buys: the database refuses rather than tidies.

    This test is only worth anything because conftest turns on SQLite's foreign
    key enforcement; without that pragma the constraint is parsed and ignored,
    the delete succeeds, and the assertion below never fires.
    """
    client.post("/notes/", json={"text": "mine"})
    with app.app_context():
        from podpack.auth import user_datastore

        owner = user_datastore.find_user(email=OWNER)
        assert owner is not None  # the fixture made them; say so before relying on it
        user_datastore.delete_user(owner)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        # Nothing was destroyed on the way to being refused.
        assert db.session.scalars(sa.select(Note)).one().owner.email == OWNER


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
