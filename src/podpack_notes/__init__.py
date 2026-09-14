"""The notes app.

A podpack app is a package exposing one module-level `site_app`. Everything else
about it is convention: `models.py` for its schema, `templates/<name>/` for its
templates, `data/` for anything it ships.
"""

from podpack import Section, SiteApp

from .views import blueprint

site_app = SiteApp(
    blueprint=blueprint,
    url_prefix="/notes",
    nav=(Section("Notes", "notes.index"),),
    # A note has an owner, so this app reads a table it does not define. Saying
    # so has two effects worth having: /_status attributes `user` to everyone
    # involved rather than to podpack alone, and a site that somehow lacks the
    # table refuses to boot instead of serving until the first query fails.
    needs_tables=frozenset({"user"}),
)
