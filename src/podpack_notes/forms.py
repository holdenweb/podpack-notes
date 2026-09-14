"""This app's forms.

flask-wtf, which is what podpack-pdf and podpack-qrcode already reach for, so a
site's author meets one idiom rather than three. It earns its place here for a
second reason those two do not have: this app's POST route is guarded by a
session cookie, and podpack installs no `CSRFProtect`, so nothing checks a token
site-wide. `FlaskForm` carries one in `hidden_tag()` and refuses a submission
that arrives without it -- which is enough protection precisely as long as every
form is one of these, and would not be if this one were hand-written markup.
"""

from flask_wtf import FlaskForm
from wtforms import SubmitField, TextAreaField
from wtforms.validators import DataRequired


class NoteForm(FlaskForm):
    """One note, as typed into the page.

    The field is named for the JSON key the API route already uses, so the two
    ways of creating a note cannot come to disagree about what a note's text is
    called.

    `DataRequired` rather than `InputRequired`: it counts a string of spaces as
    absent, which is the judgement `add_note` has always made about a JSON body
    carrying `"text": "   "`.
    """

    text = TextAreaField("Note", validators=[DataRequired()])
    submit = SubmitField("Add note")
