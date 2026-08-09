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
# the site's pyproject.toml
dependencies = ["podpack-notes"]

[tool.uv.sources]
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

| | |
| --- | --- |
| `GET /notes/` | the notes, in the site's own chrome |
| `GET /notes/list` | the same as JSON |
| `POST /notes/` | `{"text": "..."}` → stores a row |
| `POST /notes/uploads/<name>` | writes a file to the app's own data directory |

It ships a `welcome.md`, which podpack seeds into the app's host data directory
the first time it is installed and never again. The app then reads the *host*
copy, so editing it takes effect with no rebuild — which is the point of the
convention rather than a detail of this app.

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
