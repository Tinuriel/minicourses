"""Tests for check_lessons.py, build_site.py, build_catalog.py and course_lib.py. Stdlib only.

Run from the repo root:  python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "minicourse" / "scripts"
SAMPLE = ROOT / "tests" / "fixtures" / "sample-course"
sys.path.insert(0, str(SCRIPTS))

import check_lessons  # noqa: E402
import course_lib as cl  # noqa: E402


def run(script, *args, env=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env)


class Workspace:
    """A copy of the sample course to change in a test."""

    def __enter__(self):
        self.td = tempfile.TemporaryDirectory()
        self.ws = Path(self.td.name) / "pricing"
        shutil.copytree(SAMPLE, self.ws)
        self.lesson = self.ws / "lessons" / "01-three-options.md"
        return self

    def __exit__(self, *exc):
        self.td.cleanup()

    def edit(self, old, new):
        text = self.lesson.read_text(encoding="utf-8")
        assert old in text, old
        self.lesson.write_text(text.replace(old, new, 1), encoding="utf-8")

    def check(self):
        course = cl.load_course(self.ws)
        lab = cl.labels(course)
        known = {cl.same_page(u) for u in cl.raw_pages(self.ws)}
        return check_lessons.check_lesson(cl.parse_lesson(self.lesson, lab), course, lab, known)


class Checker(unittest.TestCase):
    def test_sample_lesson_is_clean(self):
        with Workspace() as w:
            errors, warnings, words = w.check()
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertGreater(words, 450)

    def test_cli_passes_sample_under_cp1251_locale(self):
        env = dict(os.environ, LC_ALL="ru_RU.CP1251", PYTHONUTF8="0")
        r = run("check_lessons.py", SAMPLE, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok   01-three-options.md", r.stdout)

    def test_citation_not_on_disk_fails(self):
        with Workspace() as w:
            w.edit("https://example.com/placeholder-2", "https://example.com/invented")
            errors, _, _ = w.check()
        self.assertTrue(any("нет в raw/" in e and "invented" in e for e in errors), errors)

    def test_url_variants_count_as_the_same_page(self):
        with Workspace() as w:
            w.edit("https://example.com/placeholder-2", "http://www.example.com/placeholder-2/#part")
            errors, _, _ = w.check()
        self.assertEqual(errors, [])

    def test_missing_section_fails(self):
        with Workspace() as w:
            w.edit("## Пример\n", "## Случай\n")
            errors, _, _ = w.check()
        self.assertTrue(any("Пример" in e for e in errors), errors)

    def test_summary_needs_three_points(self):
        with Workspace() as w:
            w.edit("- Первым называйте", "Первым называйте")
            errors, _, _ = w.check()
        self.assertTrue(any("3" in e for e in errors), errors)

    def test_try_needs_minutes(self):
        with Workspace() as w:
            w.edit("## Попробуйте · Быстрая победа · 10 минут", "## Попробуйте · Быстрая победа")
            errors, _, _ = w.check()
        self.assertTrue(any("времени" in e for e in errors), errors)

    def test_quiz_needs_two_questions(self):
        with Workspace() as w:
            text = w.lesson.read_text(encoding="utf-8")
            start = text.index("??? Почему верхний")
            end = text.index("## Почитать")
            w.lesson.write_text(text[:start] + text[end:], encoding="utf-8")
            errors, _, _ = w.check()
        self.assertTrue(any("вопрос" in e for e in errors), errors)

    def test_too_short_fails(self):
        with Workspace() as w:
            text = w.lesson.read_text(encoding="utf-8")
            start = text.index("### Как устроены")
            end = text.index("## Пример")
            w.lesson.write_text(text[:start] + text[end:], encoding="utf-8")
            errors, _, _ = w.check()
        self.assertTrue(any("слов" in e for e in errors), errors)

    def test_comment_hides_text(self):
        with Workspace() as w:
            w.edit("## Правило\n", "<!-- черновик https://example.com/never -->\n## Правило\n")
            errors, warnings, _ = w.check()
        self.assertEqual(errors, [])


class Style(unittest.TestCase):
    def warn(self, old, new):
        with Workspace() as w:
            w.edit(old, new)
            return w.check()[1]

    def test_straight_quotes(self):
        self.assertTrue(any("кавычки" in x for x in self.warn("«стоит ли оно того?»", '"стоит ли оно того?"')))

    def test_hyphen_as_dash(self):
        self.assertTrue(any("тире" in x for x in self.warn("вопрос — да или нет", "вопрос - да или нет")))

    def test_calque(self):
        self.assertTrue(any("калька" in x for x in self.warn("Если предложить три варианта, вопрос меняется.",
                                                               "Если предложить три варианта, это делает разницу.")))

    def test_title_case_heading(self):
        self.assertTrue(any("Заглавными" in x for x in self.warn("### Как устроены три варианта",
                                                                   "### Как Устроены Три Варианта")))

    def test_mixed_address(self):
        self.assertTrue(any("ты" in x and "вы" in x for x in self.warn("Возьмите последнее", "Возьми, если тебе удобно, последнее")))

    def test_demand(self):
        self.assertTrue(any("приказ" in x for x in self.warn("Проговорите их вслух", "Вы должны проговорить их вслух")))

    def test_quotes_in_urls_and_code_are_ignored(self):
        self.assertEqual(self.warn("Обычно фрилансер", 'Обычно (`a = "b"`) фрилансер'), [])


class Markdown(unittest.TestCase):
    def test_blocks(self):
        out = cl.md("Текст **жирный** и *курсив*.\n\n- a\n- b\n  - c\n\n1. x\n2. y\n\n> one\n> two\n\n??? Q?\nA.")
        self.assertIn("<strong>жирный</strong>", out)
        self.assertIn("<em>курсив</em>", out)
        self.assertIn("<ul><li>a</li><li>b\n<ul><li>c</li></ul></li></ul>", out)
        self.assertIn("<ol><li>x</li><li>y</li></ol>", out)
        self.assertIn("<blockquote><p>one</p>\n<p>two</p></blockquote>", out)
        self.assertIn('<details class="quiz"><summary>Q?</summary>', out)

    def test_html_is_escaped(self):
        out = cl.md("<script>alert(1)</script> [x](javascript:alert(1)) & co")
        self.assertNotIn("<script>", out)
        self.assertIn("&amp; co", out)

    def test_link_with_parentheses(self):
        url = "https://ru.wikipedia.org/wiki/Меркурий_(планета)"
        self.assertIn(f'href="{url}"', cl.md(f"[Меркурий]({url})"))

    def test_plural(self):
        self.assertEqual([cl.count(n, "lesson", cl.LABELS["ru"], "ru") for n in (1, 3, 5, 11, 21, 22)],
                         ["1 урок", "3 урока", "5 уроков", "11 уроков", "21 урок", "22 урока"])


class Site(unittest.TestCase):
    def test_pilot_site(self):
        with Workspace() as w, tempfile.TemporaryDirectory() as out:
            r = run("build_site.py", w.ws, "--out", Path(out) / "pricing", "--catalog", "../")
            self.assertEqual(r.returncode, 0, r.stderr)
            site = Path(out) / "pricing"
            names = sorted(p.name for p in site.iterdir())
            self.assertEqual(names, ["01-three-options.html", "index.html", "meta.json", "rules.html", "sources.html"])
            index = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn('lang="ru"', index)
            self.assertIn("Скоро", index)                      # planned lessons are listed
            self.assertIn("Пробный урок", index)
            self.assertIn('href="01-three-options.html"', index)
            self.assertIn("8 уроков", index)
            lesson = (site / "01-three-options.html").read_text(encoding="utf-8")
            for part in ("Три варианта вместо одной цены", "Быстрая победа", 'data-mark="read-01"',
                         'class="quiz"', "https://example.com/placeholder-1"):
                self.assertIn(part, lesson)
            self.assertNotIn("fonts.googleapis", lesson)
            rules = (site / "rules.html").read_text(encoding="utf-8")
            self.assertIn("Каждую цену я называю", rules)
            sources = (site / "sources.html").read_text(encoding="utf-8")
            self.assertIn("Как предлагать клиенту варианты", sources)
            meta = json.loads((site / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual((meta["lessons_written"], meta["lessons_planned"]), (1, 8))
            self.assertFalse((site / "raw").exists())

            r = run("build_catalog.py", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            catalog = (Path(out) / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="pricing/index.html"', catalog)
            self.assertIn("Как назначать цену", catalog)

    def test_rebuild_removes_deleted_lessons(self):
        with Workspace() as w, tempfile.TemporaryDirectory() as out:
            site = Path(out) / "s"
            run("build_site.py", w.ws, "--out", site)
            w.lesson.unlink()
            run("build_site.py", w.ws, "--out", site)
            self.assertFalse((site / "01-three-options.html").exists())

    def test_refuses_to_build_into_workspace(self):
        with Workspace() as w:
            r = run("build_site.py", w.ws, "--out", w.ws)
            self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
