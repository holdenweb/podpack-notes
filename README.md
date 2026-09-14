# podpack-notes

A small notes app for [podpack](https://github.com/holdenweb/podpack) sites, and
the worked example of what an app is.

It is deliberately not a stub: it has a model, a template, shipped data, per-app
configuration and a nav entry, which between them exercise every part of the
registry a real app would use.

## Installing it into a site

Add the distribution as a dependency, then the **import** name to the site's app
list:

```toml
# the site's pyproject.toml -- both, because an app does not pull in its framework
dependencies = ["podpack", "podpack-notes"]

[tool.uv.sources]
podpack = { git = "https://github.com/holdenweb/podpack.git" }
podpack-notes = { git = "https://github.com/holdenweb/podpack-notes.git" }
```

```toml
# the site's config/app.toml
[site]
apps = ["podpack_notes"]

[apps.notes]        # keyed by the app's name, not its import name
page_size = 20
```

Three spellings of one thing, and they are not interchangeable:

| | |
| --- | --- |
| `podpack-notes` | the distribution — what you depend on |
| `podpack_notes` | the import name — what goes in `apps` |
| `notes` | the app's own name, from its blueprint — what keys `[apps.notes]`, `[site.mounts]`, and its directories on disk |

A site that wants it somewhere other than `/notes` says so in `[site.mounts]`;
the app is not consulted and its nav entry follows anyway, because a `Section`
names an endpoint rather than a path.

## What it gives the site

A note belongs to the user who wrote it, and a user sees only their own.

| | |
| --- | --- |
| `GET /notes/` | the caller's notes, in the site's own chrome |
| `GET /notes/list` | the same as JSON |
| `POST /notes/` | `{"text": "..."}` → stores a row owned by the caller |
| `POST /notes/uploads/<name>` | writes a file to the app's own data directory |

The first three need a signed-in user — a browser session, or an
`Authentication-Token` header carrying the token flask-security returns from a
JSON POST to `/login?include_auth_token` (it withholds it without that
parameter). flask-security answers an unauthenticated page request with a
redirect to `/login` and an unauthenticated API call with a 401, and podpack
installs it on every site, so a site has a login already. The upload
route is unguarded: those files land in the app's one shared data directory and
have never been anybody's in particular.

Notes are owned through podpack's own `user` table, which this app declares in
`needs_tables` rather than defining. A site that installs it therefore needs at
least one user before anybody can write anything:

```bash
flask --app <site> users create you@example.com --active
```

It ships a `welcome.md`, which podpack seeds into the app's host data directory
the first time it is installed and never again. The app then reads the *host*
copy, so editing it takes effect with no rebuild — which is the point of the
convention rather than a detail of this app.

## Upgrading a site to a version that owns its notes

**This app ships no migrations, and cannot.** There is one alembic history per
site (podpack ADR-0009), so a site generates this app's schema into its own
history and nothing will remind it to. Adding the owner column is a change a site
has to make deliberately:

```bash
uv run alembic revision --autogenerate -m "notes: notes belong to a user"
```

Run that with the site's **full** app list enabled — with an app disabled,
alembic faithfully proposes dropping its tables — and read the revision before
applying it. `owner_id` is `NOT NULL`, so the generated `upgrade()` needs a line
adding before it:

```python
op.execute("DELETE FROM notes")   # no note predates ownership
```

That discards every existing note, which is the assumption this release was
written under. A site with notes worth keeping should instead add the column
nullable, backfill an owner into every row, and only then tighten it — a direct
`NOT NULL` add fails on a table with rows in it.

## Developing it

```bash
uv sync --all-groups
uv run pytest
uv run mypy
```

The tests build a real podpack site with this app installed, so what they prove
is that the app conforms to the contract, not merely that its own functions
work.

`pyproject.toml` points `podpack` at a sibling checkout, which is right for
local work and cannot survive a container build — a path source fails there with
`Distribution not found`. A site deploying this needs both packages from git.
