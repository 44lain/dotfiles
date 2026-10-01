"""UI texts keyed by id. Add a language = one new module + one entry in LANGS."""
from installer.messages import en, pt_br

LANGS = {"en": en.MESSAGES, "pt_br": pt_br.MESSAGES}


def normalize(lang) -> str:
    return "pt_br" if (lang or "").lower().replace("-", "_").startswith("pt") else "en"


def detect(env) -> str:
    return normalize(env.get("LC_ALL") or env.get("LC_MESSAGES") or env.get("LANG") or "")


def translator(lang):
    table = LANGS[normalize(lang)]

    def t(key, **kw):
        text = table.get(key) or en.MESSAGES.get(key) or key
        return text.format(**kw) if kw else text

    return t
