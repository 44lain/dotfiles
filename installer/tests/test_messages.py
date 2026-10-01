import re
import unittest
from pathlib import Path

from installer import messages
from installer.messages import en, pt_br
from installer.validate import Result  # noqa: F401  (codes are checked below)

PKG = Path(__file__).resolve().parents[1]


class Tables(unittest.TestCase):
    def test_same_keys_in_both_languages(self):
        self.assertEqual(set(en.MESSAGES), set(pt_br.MESSAGES))

    def test_no_empty_texts(self):
        for table in (en.MESSAGES, pt_br.MESSAGES):
            for k, v in table.items():
                self.assertTrue(v.strip(), k)

    def test_same_placeholders_in_both_languages(self):
        ph = lambda s: set(re.findall(r"\{(\w+)\}", s))
        for k in en.MESSAGES:
            self.assertEqual(ph(en.MESSAGES[k]), ph(pt_br.MESSAGES[k]), k)

    def test_every_literal_t_key_exists(self):
        used = set()
        for f in list(PKG.glob("*.py")):
            used |= set(re.findall(r"""\bt\(\s*["']([a-z_]+(?:\.[a-z_]+)*)["']""", f.read_text()))
        missing = sorted(k for k in used if k not in en.MESSAGES)
        self.assertEqual(missing, [])

    def test_every_validation_code_has_text(self):
        src = (PKG / "validate.py").read_text()
        codes = set(re.findall(r'"((?:name|email|host|wallpaper|image)\.[a-z_]+)"', src))
        self.assertEqual(sorted(c for c in codes if c not in en.MESSAGES), [])

    def test_every_scan_state_source_and_detail_has_text(self):
        for k in ("state.ok", "state.missing", "state.too_old", "state.no_source",
                  "source.distro", "source.recipe", "source.none",
                  "detail.apt_unknown", "detail.apt_too_old", "detail.no_package"):
            self.assertIn(k, en.MESSAGES)


class Translator(unittest.TestCase):
    def test_normalize(self):
        for v in ("pt_BR.UTF-8", "pt-BR", "pt", "PT_br"):
            self.assertEqual(messages.normalize(v), "pt_br", v)
        for v in ("en_US.UTF-8", "de", "", None, "C"):
            self.assertEqual(messages.normalize(v), "en", v)

    def test_detect_reads_lang(self):
        self.assertEqual(messages.detect({"LANG": "pt_BR.UTF-8"}), "pt_br")
        self.assertEqual(messages.detect({"LC_ALL": "pt_BR.UTF-8", "LANG": "en_US"}), "pt_br")
        self.assertEqual(messages.detect({}), "en")

    def test_translate_format_and_fallbacks(self):
        t = messages.translator("pt_br")
        self.assertIn("Pasta", t("prefs.wall_dir"))
        self.assertEqual(t("wallpaper.ok", count=933), pt_br.MESSAGES["wallpaper.ok"].format(count=933))
        self.assertEqual(t("no.such.key"), "no.such.key")

    def test_english_fallback_for_a_missing_key(self):
        t = messages.translator("pt_br")
        saved = pt_br.MESSAGES.pop("welcome.go")
        try:
            self.assertEqual(t("welcome.go"), en.MESSAGES["welcome.go"])
        finally:
            pt_br.MESSAGES["welcome.go"] = saved


if __name__ == "__main__":
    unittest.main()


class PlaceholderNamedKey(unittest.TestCase):
    def test_key_can_be_a_placeholder(self):
        # regression: scan.no_source uses {key}, which used to collide with t's own argument
        t = messages.translator("en")
        self.assertIn("kitty: no source", t("scan.no_source", key="kitty", detail="no source", manual="-"))
