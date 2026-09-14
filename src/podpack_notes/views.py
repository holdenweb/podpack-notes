"""Notes: the first podpack app, and the one that proves the mechanism.

It is small on purpose but not a stub -- it has a model, a template, shipped
data, per-app configuration and a nav entry, which between them exercise every
part of the registry that a real app would use. Since notes acquired an owner it
exercises one more: an app joining to podpack's `user` table, which the registry
has had a declaration for since ADR-0034 and which nothing had yet used.

`auth_required` comes from flask_security rather than from podpack, which
re-exports the `User` model and `is_admin` but no decorator. It is present by
construction even so: `create_app` installs flask-security on every site whether
or not any app asked for it. Both mechanisms are named because this app has both
kinds of caller -- a browser holding a session cookie and an API client
presenting a token -- and flask-security then answers each in its own idiom, a
redirect to /login for a page request and a 401 for a JSON one. That is why no
view below says anything about what to do when nobody is signed in.
"""

import pathlib
from logging import getLogger

import sqlalchemy as sa
from flask import Blueprint, jsonify, render_template, request
from flask.typing import ResponseReturnValue
from flask_security import auth_required, current_user

from podpack import app_config, db
from podpack.paths import data_dir

from .models import Note

logger = getLogger(__name__)

blueprint = Blueprint("notes", __name__, template_folder="templates")

WELCOME_FILE = "welcome.md"


@blueprint.route("/")
@auth_required("token", "session")
def index() -> ResponseReturnValue:
    """The app's own page, rendered in whatever chrome the site provides."""
    return render_template(
        "notes/index.html",
        title="Notes",
        notes=_recent(current_user.id),
        welcome=_welcome_text(),
    )


@blueprint.route("/list")
@auth_required("token", "session")
def list_notes() -> ResponseReturnValue:
    return jsonify(notes=[note.as_dict() for note in _recent(current_user.id)])


@blueprint.route("/", methods=["POST"])
@auth_required("token", "session")
def add_note() -> ResponseReturnValue:
    """Persist a note, i.e. write to the host-mapped database directory."""
    text = (request.get_json(silent=True) or {}).get("text", "").strip()
    if not text:
        return jsonify(error="a non-empty 'text' field is required"), 400
    note = Note(text=text, owner_id=current_user.id)
    db.session.add(note)
    db.session.commit()
    logger.info("stored note of %d characters for user %s", len(text), current_user.id)
    return jsonify(stored=note.as_dict()), 201


@blueprint.route("/uploads/<name>", methods=["POST"])
def store_file(name: str) -> ResponseReturnValue:
    """Persist a file in this app's own directory under the host data root.

    The app never learns where that is: `data_dir()` resolves it, so moving the
    root at deployment time is a change to the environment and to nothing else.

    Unguarded, and not by oversight: uploads land in the app's one shared data
    directory and have never been anybody's in particular. Giving a file an owner
    is a separate question from giving a note one.
    """
    target = data_dir() / pathlib.Path(name).name
    target.write_bytes(request.get_data())
    return jsonify(stored=target.name, bytes=target.stat().st_size), 201


def _recent(owner_id: int) -> list[Note]:
    """That user's most recent notes, however many this site asks for.

    The owner arrives as an argument rather than being read from `current_user`
    here, for two reasons. It says what the query needs instead of reaching into
    request state for it; and `current_user` outside a login is flask-login's
    anonymous user, which has no `id` at all -- so reading it here would turn
    every call from outside a guarded view into an AttributeError.
    """
    limit = app_config().get("page_size", 20)
    return list(
        db.session.scalars(
            sa.select(Note)
            .where(Note.owner_id == owner_id)
            .order_by(Note.created.desc())
            .limit(limit)
        )
    )


def _welcome_text() -> str | None:
    """Read the shipped welcome note back from the *host* copy.

    The app ships this file in its `data/` directory and the registry seeds it
    to the host on first install. Reading the host copy rather than the packaged
    one is what makes it editable: change it on the host, reload the page, and
    the change is there with no rebuild -- the same property the mounted config
    files have.
    """
    path = data_dir() / WELCOME_FILE
    try:
        return path.read_text()
    except OSError:
        return None
