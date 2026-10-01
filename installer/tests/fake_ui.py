"""Scripted UI for screen tests: answers are consumed in order by widget type."""
from contextlib import contextmanager

from installer.ui import BACK, CANCEL  # noqa: F401


class FakeUI:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.events = []     # ("info"|"success"|"warn"|"error"|"title"|"table", text)
        self.asked = []      # ("menu"|"checklist"|"text"|"confirm", prompt)
        self.suspended = []  # argv of suspend() calls
        self.suspend_rc = 0

    def _next(self, kind, prompt):
        self.asked.append((kind, prompt))
        return self.answers.pop(0) if self.answers else CANCEL

    def title(self, step, total, text):
        self.events.append(("title", f"{step}/{total} {text}"))

    def info(self, text):
        self.events.append(("info", text))

    def success(self, text):
        self.events.append(("success", text))

    def warn(self, text):
        self.events.append(("warn", text))

    def error(self, text):
        self.events.append(("error", text))

    def table(self, header, rows):
        self.events.append(("table", repr(rows)))
        return self._next("table", "")

    def menu(self, prompt, options, default=0):
        self.last_options = options
        return self._next("menu", prompt)

    def checklist(self, prompt, items):
        self.last_items = items
        return self._next("checklist", prompt)

    def text(self, prompt, default="", validate=None):
        self.last_default = default
        v = self._next("text", prompt)
        if validate and isinstance(v, str):
            ok, msg = validate(v)
            self.events.append(("validated", f"{ok}:{msg}"))
        return v

    def confirm(self, prompt, default=False):
        return self._next("confirm", prompt)

    @contextmanager
    def progress(self, label):
        self.events.append(("progress", label))
        yield lambda line="": self.events.append(("push", line))

    def suspend(self, argv):
        self.suspended.append(list(argv))
        return self.suspend_rc

    def close(self):
        pass

    def text_of(self, kind):
        return "\n".join(t for k, t in self.events if k == kind)
