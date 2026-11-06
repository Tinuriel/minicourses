"""Build the course website from a workspace.

Reads course.json (title, arcs, the planned lessons), lessons/NN-handle.md and the
saved pages in raw/, and writes a static site:

  index.html        course page: what it is, parts, every planned lesson, progress
  NN-handle.html    one page per written lesson
  rules.html        "my rules": the rule of every lesson, to tick and print
  sources.html      every page the course was built from, and which lessons cite it
  meta.json         a summary for build_catalog.py

Every page carries its own CSS and JS, so the folder works from disk, from any
static host (GitHub Pages, Netlify, Render, Cloudflare Pages) or as a claude.ai
artifact. Marks (read, tried, rules kept) live in the reader's browser only.

Lessons planned in course.json but not written yet are listed as "coming", so
the same command builds the pilot (one lesson) and the full course.

Usage: python3 build_site.py <workspace> [--out DIR] [--catalog URL]
  --out      default <workspace>/site
  --catalog  link to a page listing all courses (for docs/<slug>/ use "../")
"""
import datetime
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_lib as cl  # noqa: E402
import site_theme as th  # noqa: E402

e = html.escape


def lesson_href(lesson):
    return f"{lesson['n']:02d}-{lesson['handle']}.html"


class Site:
    def __init__(self, ws, catalog=""):
        self.ws = Path(ws)
        self.course = cl.load_course(ws)
        self.lab = cl.labels(self.course)
        self.ui = self.lab["ui"]
        self.lang = self.course["language"]
        self.lessons = cl.load_lessons(ws, self.lab)
        self.by_n = {l["n"]: l for l in self.lessons}
        self.pages = cl.raw_pages(ws)
        self.catalog = catalog
        self.slug = self.course["slug"]
        self.emoji = self.course.get("emoji", "📘")
        self.base_url = self.course.get("site_url", "").rstrip("/")
        planned = sorted(self.course["lessons"], key=lambda l: int(l["n"]))
        known = {int(l["n"]) for l in planned}
        # A lesson file that course.json doesn't list still gets its page.
        planned += [{"n": l["n"], "handle": l["handle"], "title": l["title"], "arc": 0}
                    for l in self.lessons if l["n"] not in known]
        self.planned = sorted(planned, key=lambda l: int(l["n"]))

    # ------------------------------------------------------------ pieces
    def count(self, n, what):
        return cl.count(n, what, self.lab, self.lang)

    def title_of(self, item):
        written = self.by_n.get(int(item["n"]))
        return (written and written["title"]) or item.get("title", "")

    def arc_title(self, k):
        arcs = self.course["arcs"]
        if 1 <= k <= len(arcs):
            return f"{self.ui['part']} {k}. {arcs[k - 1]['title']}"
        return ""

    def brand(self):
        return (f'<a class="brand" href="index.html"><span class="e" aria-hidden="true">{e(self.emoji)}</span>'
                f'{e(self.course["title"])}</a>')

    def nav(self, current):
        items = [("index.html", self.ui["nav_lessons"]), ("rules.html", self.ui["nav_rules"]),
                 ("sources.html", self.ui["nav_sources"])]
        if self.catalog:
            items.append((self.catalog, self.ui["all_courses"]))
        cur = ' aria-current="page"'
        return "".join(f'<a href="{e(h)}"{cur if h == current else ""}>{e(t)}</a>' for h, t in items)

    def footer(self):
        today = datetime.date.today().isoformat()
        author = self.course.get("author")
        parts = [e(self.course["title"])]
        if author:
            parts.append(e(author))
        parts.append(f'{e(self.ui["updated"])}: {today}')
        parts.append(e(self.ui["made_with"]))
        return "".join(f"<span>{p}</span>" for p in parts)

    def write(self, out, name, title, description, body, og_type="website"):
        canonical = f"{self.base_url}/{'' if name == 'index.html' else name}" if self.base_url else ""
        doc = th.page(lang=self.lang, title=title, description=description, body=body, brand=self.brand(),
                      nav=self.nav(name), slug=self.slug, emoji=self.emoji, canonical=canonical,
                      lessons=",".join(f"{l['n']:02d}" for l in self.lessons), footer=self.footer(), og_type=og_type)
        (out / name).write_text(doc, encoding="utf-8")

    # ------------------------------------------------------------ index
    def lesson_card(self, item):
        n = int(item["n"])
        written = self.by_n.get(n)
        title = e(self.title_of(item))
        summary = item.get("summary", "")
        if written:
            mins = self.ui["min_read"].format(n=cl.reading_minutes(written))
            return (f'<li><a class="lcard" href="{lesson_href(written)}" data-lesson="{n:02d}">'
                    f'<span class="num">{n}</span><span class="t">{title}</span><span class="m">{e(mins)}</span>'
                    + (f'<span class="s">{cl.inline(summary)}</span>' if summary else "") + "</a></li>")
        return (f'<li><div class="lcard soon"><span class="num">{n}</span><span class="t">{title}</span>'
                f'<span class="m">{e(self.ui["soon"])}</span>'
                + (f'<span class="s">{cl.inline(summary)}</span>' if summary else "") + "</div></li>")

    def index(self, out):
        c, ui = self.course, self.ui
        total_min = sum(cl.reading_minutes(l) for l in self.lessons)
        planned_n = len(self.planned)
        avg = round(total_min / len(self.lessons)) if self.lessons else 0
        stats = [self.count(planned_n, "lesson")]
        if avg:
            stats.append(ui["min_read"].format(n=f"≈{avg}") if planned_n > len(self.lessons)
                         else f"≈ {self.count(total_min, 'minute')}")
        if self.pages:
            stats.append(self.count(len(self.pages), "source"))
        if c.get("level"):
            stats.append(f'{ui["level"]}: {c["level"]}')
        first = self.lessons[0] if self.lessons else None
        cta = (f'<a class="btn" href="{lesson_href(first)}" data-cta data-continue="{e(ui["continue"])}">'
               f'{e(ui["start"])}</a>') if first else ""
        body = [f'<div class="wrap wide"><section class="hero">',
                f'<h1>{e(c["title"])}</h1>']
        if c.get("subtitle") or c.get("description"):
            body.append(f'<p class="lead">{cl.inline(c.get("subtitle") or c.get("description"))}</p>')
        body.append('<ul class="stats">' + "".join(f"<li>{e(s)}</li>" for s in stats) + "</ul>")
        body.append(cta)
        if self.lessons:
            body.append(f'<div class="progress"><div class="bar"><span data-progress-bar></span></div>'
                        f'<p data-progress-text data-template="{e(ui["progress"])}"></p></div>')
        if 0 < len(self.lessons) < planned_n:
            body.append(f'<p class="note">{e(ui["pilot"])}</p>')
        body.append(f'<p class="how">{cl.inline(c.get("how") or ui["how"])}</p></section>')

        arcs = c["arcs"]
        groups = []
        if arcs:
            for k, arc in enumerate(arcs, 1):
                groups.append((self.arc_title(k), arc.get("why", ""), [l for l in self.planned if int(l.get("arc", 0)) == k]))
            rest = [l for l in self.planned if not 1 <= int(l.get("arc", 0)) <= len(arcs)]
            if rest:
                groups.append(("", "", rest))
        else:
            groups.append(("", "", self.planned))
        for title, why, items in groups:
            if not items:
                continue
            body.append('<section class="arc">')
            if title:
                body.append(f"<h2>{e(title)}</h2>")
            if why:
                body.append(f'<p class="why">{cl.inline(why)}</p>')
            body.append('<ol class="lessons">' + "".join(self.lesson_card(l) for l in items) + "</ol></section>")

        if c["splits"]:
            body.append(f'<section class="arc"><h2>{e(ui["splits"])}</h2>')
            for s in c["splits"]:
                body.append('<div class="card split">'
                            f'<h3>{cl.inline(s.get("question", ""))}</h3>')
                sides = s.get("sides", [])
                if sides:
                    body.append("<ul>" + "".join(f"<li>{cl.inline(x)}</li>" for x in sides) + "</ul>")
                if s.get("how_to_decide"):
                    body.append(f'<p class="decide"><strong>{e(ui["how_to_decide"])}:</strong> '
                                f'{cl.inline(s["how_to_decide"])}</p>')
                body.append("</div>")
            body.append("</section>")
        body.append("</div>")
        self.write(out, "index.html", c["title"], c.get("description") or c.get("subtitle") or c["title"], "".join(body))

    # ------------------------------------------------------------ lesson
    def lesson_page(self, out, lesson, prev, nxt):
        ui, names, secs = self.ui, self.lab["sections"], lesson["sections"]
        n = lesson["n"]
        item = next((l for l in self.planned if int(l["n"]) == n), {})
        arc = self.arc_title(int(item.get("arc", 0) or 0))
        b = ['<article class="wrap lesson">',
             f'<nav class="crumbs"><a href="index.html">{e(ui["nav_lessons"])}</a>'
             + (f" · {e(arc)}" if arc else "") + "</nav>",
             f'<p class="eyebrow"><span>{e(ui["lesson"])} {n} {e(ui["of"])} {len(self.planned)}</span>'
             f'<span>{e(ui["min_read"].format(n=cl.reading_minutes(lesson)))}</span></p>',
             f"<h1>{e(lesson['title'])}</h1>"]

        def section(sid, cls, inner_html, head=True):
            h = f"<h2>{e(names[sid])}</h2>" if head else ""
            b.append(f'<section class="{cls}">{h}{inner_html}</section>')

        if "summary" in secs:
            section("summary", "card summary", cl.md(secs["summary"]))
        if "body" in secs:
            section("body", "prose", cl.md(secs["body"], heading_shift=1))
        for i, head in enumerate(lesson["unknown"], 1):
            b.append(f'<section class="prose"><h2>{cl.inline(head)}</h2>{cl.md(secs.get(f"x{i}", ""), 1)}</section>')
        if "example" in secs:
            section("example", "prose example", cl.md(secs["example"], heading_shift=1))
        if "sources" in secs:
            section("sources", "sources-note", cl.md(secs["sources"]))
        if "try" in secs:
            chips = "".join(f'<span class="chip">{e(p)}</span>' for p in lesson["try_parts"])
            b.append(f'<section class="card try"><div class="try-head"><h2>{e(names["try"])}</h2>{chips}</div>'
                     f'{cl.md(secs["try"], heading_shift=1)}</section>')
        if "rule" in secs:
            rule = re.sub(r"\s+", " ", secs["rule"]).strip()
            b.append(f'<section class="card rule"><h2>{e(names["rule"])}</h2><p class="text">{cl.inline(rule)}</p>'
                     f'<label class="check"><input type="checkbox" data-mark="rule-{n:02d}"> {e(ui["keep_rule"])}</label>'
                     "</section>")
        if "quiz" in secs:
            section("quiz", "quiz-sec", f'<p class="hint">{e(ui["answer_hint"])}</p>' + cl.md(secs["quiz"]))
        if "further" in secs:
            section("further", "further", cl.md(secs["further"]))
        b.append(f'<div class="marks"><button class="toggle" type="button" data-mark="read-{n:02d}">{e(ui["mark_read"])}</button>'
                 f'<button class="toggle" type="button" data-mark="tried-{n:02d}">{e(ui["mark_tried"])}</button></div>')
        b.append(f'<p class="skip">{e(ui["skip"])}</p>')
        pager = []
        if prev:
            pager.append(f'<a class="prev" href="{lesson_href(prev)}"><small>← {e(ui["prev"])}</small>{e(prev["title"])}</a>')
        if nxt:
            pager.append(f'<a class="next" href="{lesson_href(nxt)}"><small>{e(ui["next"])} →</small>{e(nxt["title"])}</a>')
        if pager:
            b.append('<nav class="pager">' + "".join(pager) + "</nav>")
        b.append("</article>")
        bullets = re.findall(r"^[-*] (.+)$", secs.get("summary", ""), re.M)
        desc = lesson["meta"].get("description") or item.get("summary") or (bullets[0] if bullets else lesson["title"])
        desc = re.sub(r"[*_`]", "", desc)
        self.write(out, lesson_href(lesson), f"{lesson['title']} · {self.course['title']}", desc, "".join(b), "article")

    # ------------------------------------------------------------ rules, sources
    def rules(self, out):
        ui = self.ui
        b = [f'<div class="wrap"><h1>{e(ui["rules_title"])}</h1><p class="lead how">{e(ui["rules_intro"])}</p>',
             f'<div class="toolbar"><button class="plain-btn" type="button" data-print>{e(ui["print"])}</button>'
             f'<button class="plain-btn" type="button" data-reset data-confirm="{e(ui["reset_confirm"])}">{e(ui["reset"])}</button></div>']
        items = []
        for l in self.lessons:
            rule = re.sub(r"\s+", " ", l["sections"].get("rule", "")).strip()
            if rule:
                items.append(f'<li><div class="card"><span class="text">{cl.inline(rule)}</span>'
                             f'<span class="from"><a href="{lesson_href(l)}">{e(ui["lesson"])} {l["n"]}. {e(l["title"])}</a></span>'
                             f'<label class="check"><input type="checkbox" data-mark="rule-{l["n"]:02d}"> {e(ui["keep_rule"])}</label>'
                             "</div></li>")
        b.append(f'<ol class="rules-list">{"".join(items)}</ol>' if items else f"<p>{e(ui['rules_empty'])}</p>")
        b.append("</div>")
        self.write(out, "rules.html", f"{ui['rules_title']} · {self.course['title']}", ui["rules_intro"], "".join(b))

    def sources(self, out):
        ui = self.ui
        cited = {}
        for l in self.lessons:
            for u in cl.cited_urls("\n".join(l["sections"].values())):
                cited.setdefault(cl.same_page(u), set()).add(l["n"])
        rows = []
        for url, title in self.pages.items():
            ns = sorted(cited.get(cl.same_page(url), ()))
            rows.append((-len(ns), (title or url).lower(), url, title, ns))
        rows.sort()
        b = [f'<div class="wrap"><h1>{e(ui["sources_title"])}</h1><p class="lead how">{e(ui["sources_intro"])}</p>',
             '<ul class="src">']
        for _, _, url, title, ns in rows:
            links = ", ".join(f'<a href="{lesson_href(self.by_n[n])}">{n}</a>' for n in ns)
            b.append(f'<li><a href="{e(url)}" rel="noopener" target="_blank">{e(title or url)}</a> '
                     f'<span class="d">{e(cl.domain(url))}</span>'
                     + (f'<div class="in">{e(ui["cited_in"])}: {links}</div>' if ns else "") + "</li>")
        b.append("</ul></div>")
        self.write(out, "sources.html", f"{ui['sources_title']} · {self.course['title']}", ui["sources_intro"], "".join(b))

    # ------------------------------------------------------------ all
    def build(self, out):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        for old in out.glob("[0-9][0-9]-*.html"):
            old.unlink()
        self.index(out)
        for i, l in enumerate(self.lessons):
            self.lesson_page(out, l, self.lessons[i - 1] if i else None,
                             self.lessons[i + 1] if i + 1 < len(self.lessons) else None)
        self.rules(out)
        self.sources(out)
        meta = {
            "slug": self.slug, "title": self.course["title"],
            "description": self.course.get("description") or self.course.get("subtitle", ""),
            "language": self.lang, "level": self.course.get("level", ""), "emoji": self.emoji,
            "lessons_written": len(self.lessons), "lessons_planned": len(self.planned),
            "minutes": sum(cl.reading_minutes(l) for l in self.lessons),
            "sources": len(self.pages), "updated": datetime.date.today().isoformat(),
        }
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return out, meta


def main(argv):
    if not argv:
        sys.exit(__doc__)
    sys.stdout.reconfigure(errors="replace")
    ws = Path(argv[0]).expanduser().resolve()
    out = Path(argv[argv.index("--out") + 1]).expanduser() if "--out" in argv else ws / "site"
    catalog = argv[argv.index("--catalog") + 1] if "--catalog" in argv else ""
    if out.resolve() == ws:
        sys.exit("--out must not be the workspace itself")
    if (out / "raw").exists():
        sys.exit(f"{out} holds a raw/ folder; refusing to build over research files")
    site = Site(ws, catalog)
    if not site.lessons:
        print("warning: no lessons yet (lessons/NN-handle.md); building the course page only")
    out, meta = site.build(out)
    print(f"site: {out}  ({meta['lessons_written']} of {meta['lessons_planned']} lessons, "
          f"{meta['minutes']} min of reading, {meta['sources']} sources)")
    print(f"open: {out / 'index.html'}")


if __name__ == "__main__":
    main(sys.argv[1:])
