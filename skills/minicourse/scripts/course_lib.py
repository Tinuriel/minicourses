"""Shared code for check_lessons.py, build_site.py and build_catalog.py. Stdlib only.

- LABELS: section names and interface strings per course language (ru, uk, en).
  A course in another language adds its own under "labels" in course.json,
  in the same shape as LABELS["en"]; anything missing falls back to English.
- load_course / load_lessons / parse_lesson: read a workspace.
- md(): a small Markdown renderer for the subset lessons use.
"""
import html
import json
import math
import re
from pathlib import Path

SECTIONS = ["summary", "body", "example", "sources", "try", "rule", "quiz", "further"]

LABELS = {
    "ru": {
        "sections": {
            "summary": "Коротко", "body": "Разбор", "example": "Пример",
            "sources": "Что говорят источники", "try": "Попробуйте", "rule": "Правило",
            "quiz": "Проверьте себя", "further": "Почитать подробнее",
        },
        "energy": ["Быстрая победа", "Глубокий фокус", "С людьми", "Организационное"],
        "plural": {"lesson": ["урок", "урока", "уроков"], "source": ["источник", "источника", "источников"],
                   "minute": ["минута", "минуты", "минут"]},
        "ui": {
            "lesson": "Урок", "of": "из", "part": "Часть", "min_read": "{n} мин чтения",
            "nav_lessons": "Уроки", "nav_rules": "Мои правила", "nav_sources": "Источники",
            "mark_read": "Прочитано", "mark_tried": "Попробовано", "keep_rule": "Беру в свои правила",
            "soon": "Скоро", "prev": "Назад", "next": "Дальше", "start": "Начать с первого урока",
            "continue": "Продолжить", "level": "Уровень",
            "progress": "Прочитано: {read} из {total} · попробовано: {tried} · правил: {kept}",
            "splits": "Где источники расходятся", "how_to_decide": "Как выбрать",
            "rules_title": "Мои правила",
            "rules_intro": "По одному правилу из каждого урока. Отметьте те, что берёте себе, и распечатайте список: он останется с вами, когда курс закончится.",
            "rules_empty": "Правила появятся здесь, когда будут готовы уроки.",
            "sources_title": "Источники курса",
            "sources_intro": "Страницы, которые прочитали при подготовке курса. Каждый факт в уроках ведёт к одной из них.",
            "cited_in": "В уроках", "show_answer": "Ответ",
            "skip": "Урок можно пропустить: ничего не сгорит, следующий урок просто следующий.",
            "how": "Каждый урок читается за несколько минут, разбирает одну идею и заканчивается небольшой практикой и правилом, которое стоит оставить себе. Уроки можно читать в любом порядке и с любыми паузами.",
            "theme": "Сменить тему", "print": "Распечатать", "reset": "Сбросить отметки",
            "reset_confirm": "Сбросить все отметки этого курса?",
            "made_with": "Курс собран навыком minicourse", "updated": "Обновлено",
            "all_courses": "Все курсы", "catalog_title": "Мини-курсы",
            "catalog_intro": "Короткие текстовые курсы: несколько минут чтения, одна практика и одно правило в каждом уроке.",
            "catalog_empty": "Курсов пока нет.",
            "pilot": "Пробный урок. Остальные появятся, если формат подойдёт.",
            "contents": "Содержание", "answer_hint": "Подумайте, потом откройте",
        },
    },
    "uk": {
        "sections": {
            "summary": "Коротко", "body": "Розбір", "example": "Приклад",
            "sources": "Що кажуть джерела", "try": "Спробуйте", "rule": "Правило",
            "quiz": "Перевірте себе", "further": "Почитати докладніше",
        },
        "energy": ["Швидка перемога", "Глибокий фокус", "З людьми", "Організаційне"],
        "plural": {"lesson": ["урок", "уроки", "уроків"], "source": ["джерело", "джерела", "джерел"],
                   "minute": ["хвилина", "хвилини", "хвилин"]},
        "ui": {
            "lesson": "Урок", "of": "з", "part": "Частина", "min_read": "{n} хв читання",
            "nav_lessons": "Уроки", "nav_rules": "Мої правила", "nav_sources": "Джерела",
            "mark_read": "Прочитано", "mark_tried": "Спробувано", "keep_rule": "Беру до своїх правил",
            "soon": "Незабаром", "prev": "Назад", "next": "Далі", "start": "Почати з першого уроку",
            "continue": "Продовжити", "level": "Рівень",
            "progress": "Прочитано: {read} з {total} · спробувано: {tried} · правил: {kept}",
            "splits": "Де джерела розходяться", "how_to_decide": "Як обрати",
            "rules_title": "Мої правила",
            "rules_intro": "По одному правилу з кожного уроку. Позначте ті, що берете собі, і роздрукуйте список: він залишиться з вами, коли курс закінчиться.",
            "rules_empty": "Правила з'являться тут, коли будуть готові уроки.",
            "sources_title": "Джерела курсу",
            "sources_intro": "Сторінки, які прочитали під час підготовки курсу. Кожен факт в уроках веде до однієї з них.",
            "cited_in": "В уроках", "show_answer": "Відповідь",
            "skip": "Урок можна пропустити: нічого не згорить, наступний урок просто наступний.",
            "how": "Кожен урок читається за кілька хвилин, розбирає одну ідею і закінчується невеликою практикою та правилом, яке варто залишити собі. Уроки можна читати в будь-якому порядку і з будь-якими паузами.",
            "theme": "Змінити тему", "print": "Роздрукувати", "reset": "Скинути позначки",
            "reset_confirm": "Скинути всі позначки цього курсу?",
            "made_with": "Курс зібрано навичкою minicourse", "updated": "Оновлено",
            "all_courses": "Усі курси", "catalog_title": "Міні-курси",
            "catalog_intro": "Короткі текстові курси: кілька хвилин читання, одна практика і одне правило в кожному уроці.",
            "catalog_empty": "Курсів поки немає.",
            "pilot": "Пробний урок. Решта з'явиться, якщо формат підійде.",
            "contents": "Зміст", "answer_hint": "Подумайте, потім відкрийте",
        },
    },
    "en": {
        "sections": {
            "summary": "In short", "body": "The idea", "example": "Example",
            "sources": "What the sources say", "try": "Try it", "rule": "Rule to keep",
            "quiz": "Check yourself", "further": "Go deeper",
        },
        "energy": ["Quick Win", "Deep Focus", "People", "Admin"],
        "plural": {"lesson": ["lesson", "lessons"], "source": ["source", "sources"], "minute": ["minute", "minutes"]},
        "ui": {
            "lesson": "Lesson", "of": "of", "part": "Part", "min_read": "{n} min read",
            "nav_lessons": "Lessons", "nav_rules": "My rules", "nav_sources": "Sources",
            "mark_read": "Read", "mark_tried": "Tried", "keep_rule": "Keep this rule",
            "soon": "Coming", "prev": "Previous", "next": "Next", "start": "Start with lesson 1",
            "continue": "Continue", "level": "Level",
            "progress": "Read: {read} of {total} · tried: {tried} · rules kept: {kept}",
            "splits": "Where the sources disagree", "how_to_decide": "How to choose",
            "rules_title": "My rules",
            "rules_intro": "One rule from each lesson. Tick the ones you keep and print the list: it stays with you after the course ends.",
            "rules_empty": "Rules appear here once the lessons are written.",
            "sources_title": "Course sources",
            "sources_intro": "The pages read while making this course. Every fact in the lessons goes back to one of them.",
            "cited_in": "In lessons", "show_answer": "Answer",
            "skip": "Skipping costs nothing: the next lesson is just the next lesson.",
            "how": "Each lesson takes a few minutes to read, covers one idea and ends with a small thing to try and a rule worth keeping. Read them in any order, with any breaks.",
            "theme": "Switch theme", "print": "Print", "reset": "Reset marks",
            "reset_confirm": "Reset all marks for this course?",
            "made_with": "Made with the minicourse skill", "updated": "Updated",
            "all_courses": "All courses", "catalog_title": "Mini-courses",
            "catalog_intro": "Short text courses: a few minutes of reading, one practice and one rule per lesson.",
            "catalog_empty": "No courses yet.",
            "pilot": "Pilot lesson. The rest follow if the format works.",
            "contents": "Contents", "answer_hint": "Think first, then open",
        },
    },
}


def labels(course):
    """Labels for the course language, with course.json "labels" on top and English underneath."""
    lang = course.get("language", "ru")
    base = json.loads(json.dumps(LABELS["en"]))
    for layer in (LABELS.get(lang, {}), course.get("labels", {})):
        for key, value in layer.items():
            if isinstance(value, dict):
                base.setdefault(key, {}).update(value)
            else:
                base[key] = value
    return base


def plural(n, forms, lang):
    if len(forms) == 3 and lang in ("ru", "uk", "be"):
        if n % 10 == 1 and n % 100 != 11:
            return forms[0]
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return forms[1]
        return forms[2]
    return forms[0] if n == 1 else forms[-1]


def count(n, what, lab, lang):
    return f"{n} {plural(n, lab['plural'][what], lang)}"


# ---------------------------------------------------------------- workspace

def load_course(ws):
    path = Path(ws) / "course.json"
    if not path.exists():
        raise SystemExit(f"no course.json in {ws}")
    course = json.loads(path.read_text(encoding="utf-8"))
    course.setdefault("language", "ru")
    course.setdefault("slug", Path(ws).resolve().name)
    course.setdefault("arcs", [])
    course.setdefault("lessons", [])
    course.setdefault("splits", [])
    return course


def lesson_files(ws):
    return sorted(p for p in (Path(ws) / "lessons").glob("[0-9][0-9]-*.md") if p.is_file())


def split_front(text):
    """Simple `key: value` front matter between --- lines; values may be "quoted"."""
    meta = {}
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                key, sep, value = line.partition(":")
                if sep and key.strip():
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                        value = value[1:-1]
                    meta[key.strip()] = value
            text = text[end + 4:].lstrip("\n")
    return meta, text


def section_id(heading, lab):
    head = heading.strip().lower()
    for sid, name in lab["sections"].items():
        if head == name.lower() or head.startswith(name.lower() + " ") or head.startswith(name.lower() + "·"):
            return sid
    return None


def parse_lesson(path, lab):
    """-> dict(meta, title, sections{id: markdown}, order[ids], unknown[headings], try_parts[...])."""
    text = re.sub(r"<!--.*?-->", "", Path(path).read_text(encoding="utf-8"), flags=re.S)
    meta, body = split_front(text)
    sections, order, unknown, try_parts = {}, [], [], []
    current, buf = None, []
    preamble = []

    def flush():
        if current:
            sections[current] = "\n".join(buf).strip()

    for line in body.splitlines():
        m = re.match(r"^## +(.+?)\s*$", line)
        if m:
            flush()
            heading = m.group(1)
            current = section_id(heading, lab)
            buf = []
            if current is None:
                unknown.append(heading)
                current = f"x{len(unknown)}"
            else:
                order.append(current)
                if current == "try":
                    try_parts = [p.strip() for p in re.split(r"\s+·\s+", heading)[1:] if p.strip()]
        elif current is None:
            preamble.append(line)
        else:
            buf.append(line)
    flush()
    name = Path(path).stem
    num = int(name[:2])
    return {"path": Path(path), "n": num, "handle": name[3:], "meta": meta,
            "title": meta.get("title", ""), "sections": sections, "order": order,
            "unknown": unknown, "try_parts": try_parts, "preamble": "\n".join(preamble).strip()}


def load_lessons(ws, lab):
    return [parse_lesson(p, lab) for p in lesson_files(ws)]


def words(text):
    text = re.sub(r"https?://\S+", "", text)
    return len(re.findall(r"[\w’'-]+", text))


def reading_minutes(lesson):
    if lesson["meta"].get("minutes", "").isdigit():
        return int(lesson["meta"]["minutes"])
    total = sum(words(v) for k, v in lesson["sections"].items() if k != "further")
    return max(1, math.ceil(total / 170))


def raw_pages(ws):
    """Every saved page: {url: title}. scrape.py writes UTF-8 front matter."""
    pages = {}
    for f in sorted(Path(ws).glob("raw/*/*.md")):
        meta, _ = split_front(f.read_text(encoding="utf-8", errors="replace"))
        if meta.get("url"):
            title = meta.get("title", "")
            try:
                title = json.loads(f'"{title}"') if title else title
            except json.JSONDecodeError:
                pass
            pages[meta["url"]] = title
    return pages


# ---------------------------------------------------------------- urls

URL = re.compile(r"https?://(?:[^\s()<>\[\]`«»\"]|\([^\s()<>]*\))+")
TRAILING = ".,;:!?*_'\"`"


def cited_urls(text):
    return [u.rstrip(TRAILING) for u in URL.findall(text)]


def same_page(url):
    """One key per page: scheme, www., #fragment and a trailing slash don't change the page."""
    url = url.rstrip(TRAILING)
    m = re.match(r"https?://([^/?#]+)([^#]*)", url, re.I)
    if not m:
        return url
    path, q, query = m.group(2).partition("?")
    return m.group(1).lower().removeprefix("www.") + path.rstrip("/") + q + query


def domain(url):
    m = re.match(r"https?://([^/?#]+)", url)
    return m.group(1).lower().removeprefix("www.") if m else url


# ---------------------------------------------------------------- markdown

def _inline(text, typo=True):
    keep = []

    def stash(fragment):
        keep.append(fragment)
        return f"\x00{len(keep) - 1}\x00"

    text = re.sub(r"`([^`]+)`", lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)

    def link(m):
        label, url = m.group(1), m.group(2)
        ext = ' rel="noopener" target="_blank"' if url.startswith("http") else ""
        return stash(f'<a href="{html.escape(url, quote=True)}"{ext}>{_inline(label, typo)}</a>')

    text = re.sub(r"\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)", link, text)
    text = URL.sub(lambda m: stash(
        f'<a href="{html.escape(m.group(0).rstrip(TRAILING), quote=True)}" rel="noopener" target="_blank">'
        f'{html.escape(domain(m.group(0)))}</a>' + html.escape(m.group(0)[len(m.group(0).rstrip(TRAILING)):])), text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    if typo:
        # A dash never starts a line; a one-letter word never ends one.
        text = text.replace(" — ", " — ").replace(" – ", " – ")
    return re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], text)


def inline(text):
    return _inline(text)


LIST_ITEM = re.compile(r"^(\s{0,3})([-*+]|\d+[.)])\s+(.*)$")


def md(text, heading_shift=0):
    """Render the Markdown subset lessons use: ###/#### headings, paragraphs, - and 1. lists
    (nested by indent), > quotes, ``` code, | tables, --- rules, and `??? question` lines
    followed by an answer (a self-check card)."""
    lines = text.replace("\t", "    ").splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = min(6, max(2, len(m.group(1)) + heading_shift))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        if line.startswith("???"):
            question = line[3:].strip()
            j = i + 1
            while j < len(lines) and lines[j].strip() and not lines[j].startswith("???"):
                j += 1
            answer = md("\n".join(lines[i + 1:j]))
            out.append(f'<details class="quiz"><summary>{inline(question)}</summary>'
                       f'<div class="answer">{answer}</div></details>')
            i = j
            continue
        if line.startswith(">"):
            j = i
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            # Each quoted line is its own paragraph: quotes hold templates and scripts line by line.
            inner = "\n\n".join(re.sub(r"^> ?", "", l) for l in lines[i:j])
            out.append(f"<blockquote>{md(inner)}</blockquote>")
            i = j
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]):
            def cells(row):
                return [c.strip() for c in row.strip().strip("|").split("|")]
            head = cells(line)
            j = i + 2
            rows = []
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append(cells(lines[j]))
                j += 1
            table = "<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
            table += "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f'<div class="table"><table>{table}</tbody></table></div>')
            i = j
            continue
        m = LIST_ITEM.match(line)
        if m:
            ordered = m.group(2)[0].isdigit()
            base = len(m.group(1))
            items, j = [], i
            col = base + len(m.group(2)) + 1

            def indent(s):
                return len(s) - len(s.lstrip())

            while j < len(lines):
                mm = LIST_ITEM.match(lines[j])
                if mm and len(mm.group(1)) == base and mm.group(2)[0].isdigit() == ordered:
                    items.append([mm.group(3)])
                    j += 1
                elif items and lines[j].strip() and indent(lines[j]) > base:
                    items[-1].append(lines[j][min(indent(lines[j]), col):])
                    j += 1
                elif items and not lines[j].strip() and j + 1 < len(lines) and lines[j + 1].strip() and (
                        indent(lines[j + 1]) > base or (LIST_ITEM.match(lines[j + 1]) and indent(lines[j + 1]) == base
                                                        and LIST_ITEM.match(lines[j + 1]).group(2)[0].isdigit() == ordered)):
                    items[-1].append("")
                    j += 1
                else:
                    break
            tag = "ol" if ordered else "ul"
            first = int(m.group(2)[:-1]) if ordered else 1
            start = f' start="{first}"' if first != 1 else ""
            rendered = []
            for item in items:
                inner = md("\n".join(item).strip("\n"))
                if "" not in item:
                    inner = re.sub(r"^<p>(.*?)</p>", r"\1", inner, count=1, flags=re.S)
                rendered.append(f"<li>{inner}</li>")
            out.append(f"<{tag}{start}>" + "".join(rendered) + f"</{tag}>")
            i = j
            continue
        j = i
        para = []
        while j < len(lines) and lines[j].strip() and not (
                LIST_ITEM.match(lines[j]) or lines[j].startswith(("#", ">", "```", "???"))
                or re.match(r"^\s*-{3,}\s*$", lines[j])):
            para.append(lines[j].strip())
            j += 1
        if not para:
            para, j = [line.strip()], i + 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")
        i = j
    return "\n".join(out)
