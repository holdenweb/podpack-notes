"""The notes app's schema.

Nothing imports this module explicitly. The registry imports it while installing
the app, and defining a `db.Model` subclass registers it on `db.metadata` as an
import side effect -- which is how alembic comes to know about an app's tables
without the migration environment having heard of the app.
"""

from datetime import datetime, timezone
from typing import Any

from podpack import User, db


class Note(db.Model):  # type: ignore[name-defined]  # flask-sqlalchemy builds db.Model at runtime
    """A note, belonging to exactly one user.

    Unqualified, so it lands in whatever `search_path` says. The bootstrap in
    db-init/ sets the application role's search_path to the `app` schema it owns,
    so no schema is named here -- which is also what keeps alembic free of schema
    configuration, and why the foreign key below names `user.id` and not
    `app.user.id`.

    `user` is podpack's table rather than this app's, so the app declares it in
    `needs_tables` and the site refuses to boot if nothing defines it. See
    ADR-0034: joining to a table is as real a need as defining one.
    """

    __tablename__ = "notes"

    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    owner_id = db.Column(
        db.Integer,
        # RESTRICT, where flask-security chose CASCADE for its own user-owned
        # table: deleting a user who still has notes should fail and say so
        # rather than quietly destroy what they wrote. It makes `flask users
        # delete` a two-step job, which is the point of choosing it.
        #
        # Named, because `db.metadata` carries no naming convention and an
        # anonymous constraint autogenerates a `downgrade()` reading
        # `op.drop_constraint(None, ...)` -- which no site can run.
        db.ForeignKey("user.id", ondelete="RESTRICT", name="fk_notes_owner_id_user"),
        nullable=False,
    )
    created = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # One direction, and deliberately no backref: a backref would bolt a `notes`
    # attribute onto podpack's own `User` from inside an app, which is not an
    # app's to do and would collide the day a second app did the same.
    owner = db.relationship(User)

    def as_dict(self) -> dict[str, Any]:
        # The owner is not reported. Every note a caller can see is already
        # theirs, so the id would tell them only what they knew.
        return {"id": self.id, "text": self.text, "created": self.created.isoformat()}
