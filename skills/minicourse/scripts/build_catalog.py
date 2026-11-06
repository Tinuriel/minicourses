"""Build a catalog page listing every course published in one folder.

Each course is a sub-folder built by build_site.py (it has meta.json). The
catalog is <dir>/index.html, in the same style as the courses. Use it when
several courses live on one site, e.g. GitHub Pages from docs/:

  docs/index.html            <- this script
  docs/<course-slug>/...     <- build_site.py <ws> --out docs/<course-slug> --catalog ../

Usage: python3 build_catalog.py <dir> [--lang ru] [--title "…"] [--intro "…"]
"""
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_lib as cl  # noqa: E402
import site_theme as th  # noqa: E402

e = html.escape


def main(argv):
    if not argv:
        sys.exit(__doc__)
    root = Path(argv[0]).expanduser().resolve()
    opt = {k: argv[argv.index(k) + 1] for k in ("--lang", "--title", "--intro") if k in argv}
    lang = opt.get("--lang", "ru")
    lab = cl.labels({"language": lang})
    ui = lab["ui"]
    title = opt.get("--title", ui["catalog_title"])
    intro = opt.get("--intro", ui["catalog_intro"])
    courses = []
    for meta_file in sorted(root.glob("*/meta.json")):
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        meta["dir"] = meta_file.parent.name
        courses.append(meta)
    courses.sort(key=lambda m: m.get("updated", ""), reverse=True)
    cards = []
    for m in courses:
        mlab = cl.labels({"language": m.get("language", lang)})
        bits = [cl.count(m["lessons_planned"], "lesson", mlab, m.get("language", lang))]
        if m.get("level"):
            bits.append(m["level"])
        if m["lessons_written"] < m["lessons_planned"]:
            bits.append(f'{m["lessons_written"]}/{m["lessons_planned"]}')
        cards.append(f'<li><a class="ccard" href="{e(m["dir"])}/index.html">'
                     f'<span class="e" aria-hidden="true">{e(m.get("emoji", "📘"))}</span>'
                     f'<span class="t">{e(m["title"])}</span><span class="s">{e(m.get("description", ""))}</span>'
                     f'<span class="m">{e(" · ".join(bits))}</span></a></li>')
    body = (f'<div class="wrap wide"><section class="hero"><h1>{e(title)}</h1><p class="lead">{e(intro)}</p></section>'
            + (f'<ul class="courses">{"".join(cards)}</ul>' if cards else f'<p class="how">{e(ui["catalog_empty"])}</p>')
            + "</div>")
    brand = f'<a class="brand" href="index.html"><span class="e" aria-hidden="true">📚</span>{e(title)}</a>'
    doc = th.page(lang=lang, title=title, description=intro, body=body, brand=brand, emoji="📚",
                  footer=f"<span>{e(ui['made_with'])}</span>")
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(doc, encoding="utf-8")
    (root / ".nojekyll").touch()
    print(f"catalog: {root / 'index.html'} (courses: {len(courses)})")


if __name__ == "__main__":
    main(sys.argv[1:])
