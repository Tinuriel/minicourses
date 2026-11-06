"""Regression tests for scrape.py, kept from Claudemy (MIT). Stdlib only.

Run from the repo root:  python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "minicourse" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import scrape  # noqa: E402


ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
  <title>Blogger order</title>
  <published>2024-01-02T00:00:00Z</published>
  <content type="html">short summary</content>
  <link rel="replies" type="application/atom+xml" href="https://blog.example.com/feeds/123/comments/default"/>
  <link rel="edit" type="application/atom+xml" href="https://www.blogger.com/feeds/1/posts/default/123"/>
  <link rel="self" type="application/atom+xml" href="https://www.blogger.com/feeds/1/posts/default/123"/>
  <link rel="alternate" type="text/html" href="https://blog.example.com/2024/01/my-post.html"/>
</entry>
<entry>
  <title>No rel at all</title>
  <link href="https://blog.example.com/2024/01/plain.html"/>
</entry>
<entry>
  <title>Enclosure first</title>
  <link rel="enclosure" type="audio/mpeg" href="https://blog.example.com/ep1.mp3"/>
  <link rel="alternate" type="text/html" href="https://blog.example.com/2024/01/ep1.html"/>
</entry>
<entry>
  <title>Only a self link</title>
  <link rel="self" href="https://blog.example.com/feeds/999"/>
</entry>
</feed>"""


class AtomLinks(unittest.TestCase):
    """Issue #2: the entry url is the rel="alternate" link, not the first <link>."""

    def test_prefers_alternate_over_earlier_links(self):
        urls = [it["url"] for it in scrape.feed_items(ATOM)]
        self.assertEqual(urls[0], "https://blog.example.com/2024/01/my-post.html")
        self.assertEqual(urls[1], "https://blog.example.com/2024/01/plain.html")
        self.assertEqual(urls[2], "https://blog.example.com/2024/01/ep1.html")

    def test_falls_back_to_the_only_link(self):
        urls = [it["url"] for it in scrape.feed_items(ATOM)]
        self.assertEqual(urls[3], "https://blog.example.com/feeds/999")


INDEX = """<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://site.com/post-sitemap1.xml</loc><lastmod>2024-05-01</lastmod></sitemap>
<sitemap><loc>https://site.com/post-sitemap2.xml</loc><lastmod>2024-06-01</lastmod></sitemap>
<sitemap><loc>https://site.com/page-sitemap.xml</loc></sitemap>
</sitemapindex>"""


CHILD = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://site.com/blog/{a}</loc><lastmod>{da}T10:00:00+00:00</lastmod></url>
<url><loc>https://site.com/blog/{b}</loc><lastmod>{db}</lastmod></url>
<url><loc>https://site.com/about</loc></url>
</urlset>"""


SELF_INDEX = """<sitemapindex><sitemap><loc>https://loop.com/sitemap.xml</loc></sitemap></sitemapindex>"""


class SitemapIndex(unittest.TestCase):
    """Issue #3: a sitemap index is followed instead of yielding zero posts."""

    def test_follows_child_sitemaps(self):
        pages = {
            "https://site.com/sitemap.xml": INDEX,
            "https://site.com/post-sitemap1.xml": CHILD.format(a="one", da="2024-01-05", b="two", db="2024-02-05"),
            "https://site.com/post-sitemap2.xml": CHILD.format(a="three", da="2024-03-05", b="four", db="2024-04-05"),
            "https://site.com/page-sitemap.xml": "<urlset><url><loc>https://site.com/contact</loc></url></urlset>",
        }
        site = {"sitemaps": ["https://site.com/sitemap.xml"], "url_pattern": r"site\.com/blog/"}
        with mock.patch.object(scrape, "fetch", side_effect=lambda u: pages[u]):
            entries = scrape.sitemap_entries(site)
        self.assertEqual(entries, [
            ("2024-04-05", "https://site.com/blog/four"),
            ("2024-03-05", "https://site.com/blog/three"),
            ("2024-02-05", "https://site.com/blog/two"),
            ("2024-01-05", "https://site.com/blog/one"),
        ])

    def test_plain_urlset_still_works(self):
        pages = {"https://site.com/post-sitemap1.xml": CHILD.format(a="x", da="2024-01-01", b="y", db="2024-01-02")}
        site = {"sitemaps": ["https://site.com/post-sitemap1.xml"], "url_pattern": r"site\.com/blog/"}
        with mock.patch.object(scrape, "fetch", side_effect=lambda u: pages[u]):
            entries = scrape.sitemap_entries(site)
        self.assertEqual([u for _, u in entries], ["https://site.com/blog/y", "https://site.com/blog/x"])

    def test_url_in_two_child_sitemaps_is_listed_once(self):
        # WordPress lists posts in its post sitemap and again in its image sitemap.
        pages = {
            "https://site.com/sitemap.xml": "<sitemapindex><sitemap><loc>https://site.com/posts.xml</loc></sitemap>"
                                            "<sitemap><loc>https://site.com/images.xml</loc></sitemap></sitemapindex>",
            "https://site.com/posts.xml": CHILD.format(a="one", da="2024-01-05", b="two", db="2024-02-05"),
            "https://site.com/images.xml": "<urlset><url><loc>https://site.com/blog/one</loc>"
                                           "<lastmod>2024-06-01</lastmod></url></urlset>",
        }
        site = {"sitemaps": ["https://site.com/sitemap.xml"], "url_pattern": r"site\.com/blog/"}
        with mock.patch.object(scrape, "fetch", side_effect=lambda u: pages[u]):
            entries = scrape.sitemap_entries(site)
        self.assertEqual(entries, [("2024-06-01", "https://site.com/blog/one"), ("2024-02-05", "https://site.com/blog/two")])

    def test_self_referencing_index_terminates(self):
        pages = {"https://loop.com/sitemap.xml": SELF_INDEX}
        site = {"sitemaps": ["https://loop.com/sitemap.xml"], "url_pattern": r"loop\.com/"}
        with mock.patch.object(scrape, "fetch", side_effect=lambda u: pages[u]) as f:
            entries = scrape.sitemap_entries(site)
        self.assertEqual(entries, [])
        self.assertLess(f.call_count, 10)


def quiet():
    """Capture stdout and stderr together; returns (context manager, buffer)."""
    buf = io.StringIO()
    stack = contextlib.ExitStack()
    stack.enter_context(contextlib.redirect_stdout(buf))
    stack.enter_context(contextlib.redirect_stderr(buf))
    return stack, buf


def long_html(words=300, paras=1):
    return "".join("<p>" + "word " * (words // paras) + "</p>" for _ in range(paras))


class SubstackNotJson(unittest.TestCase):
    """A Substack host answering HTML (bot check, login page) fails that author, not the run."""

    def test_other_authors_still_run(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "sources.json").write_text(json.dumps({"authors": [
                {"name": "First", "substack": "first.substack.com"},
                {"name": "Second", "substack": "second.substack.com"}]}))
            stack, buf = quiet()
            with stack, mock.patch.object(scrape, "fetch", return_value="<html>Just a moment...</html>"):
                scrape.main(ws)
            out = buf.getvalue()
        self.assertIn("First: FAILED", out)
        self.assertIn("Second: FAILED", out)
        self.assertIn("not JSON", out)


SITEMAP_TWO = ("<urlset><url><loc>https://s.com/blog/a</loc></url>"
               "<url><loc>https://s.com/blog/b</loc></url></urlset>")


THIN_PAGE = "<html><body><main>too short</main></body></html>"


class PersonModeReasons(unittest.TestCase):
    """Sitemap and RSS modes name every page they did not save, like web mode does."""

    def test_sitemap_mode_prints_reasons(self):
        pages = {"https://s.com/sitemap.xml": SITEMAP_TWO, "https://s.com/blog/a": THIN_PAGE, "https://s.com/blog/b": THIN_PAGE}
        with tempfile.TemporaryDirectory() as td:
            stack, buf = quiet()
            with stack, mock.patch.object(scrape, "fetch", side_effect=lambda u: pages[u]), \
                    mock.patch.object(scrape, "fetch_bytes", side_effect=lambda u: pages[u].encode()), \
                    mock.patch.object(scrape.time, "sleep"):
                scrape.scrape_sitemap(Path(td), {"name": "Site Person"},
                                      {"sitemaps": ["https://s.com/sitemap.xml"], "url_pattern": r"s\.com/blog/"})
        out = buf.getvalue()
        self.assertIn("thin or JavaScript-only", out)
        self.assertIn("https://s.com/blog/a", out)
        self.assertIn("https://s.com/blog/b", out)

    def test_rss_mode_prints_reasons(self):
        feed = ('<rss><channel><item><title>t</title><link>https://s.com/blog/a</link>'
                '<description>short</description></item></channel></rss>')
        with tempfile.TemporaryDirectory() as td:
            stack, buf = quiet()
            with stack, mock.patch.object(scrape, "fetch_bytes", side_effect=lambda u: (feed if u.endswith("/feed") else THIN_PAGE).encode()), \
                    mock.patch.object(scrape.time, "sleep"):
                scrape.scrape_rss(Path(td), {"name": "Feed Person"}, {"feed": "https://s.com/feed"})
        out = buf.getvalue()
        self.assertIn("thin or JavaScript-only", out)
        self.assertIn("https://s.com/blog/a", out)


class WebFilenames(unittest.TestCase):
    """Two pages that would share a filename both stay on disk."""

    def test_same_slug_same_date_keeps_both(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            web = {"name": "web"}
            scrape.write_post(out, web, "A", "undated", "https://docs.example.com/guide/intro", "word " * 200)
            scrape.write_post(out, web, "B", "undated", "https://docs.example.com/tutorial/intro", "word " * 200)
            scrape.write_post(out, web, "A again", "undated", "https://docs.example.com/guide/intro", "word " * 201)
            files = sorted(p.name for p in out.glob("*.md"))
            self.assertEqual(len(files), 2, files)
            self.assertEqual(scrape.urls_on_disk(out),
                             {"https://docs.example.com/guide/intro", "https://docs.example.com/tutorial/intro"})


class SubstackLimits(unittest.TestCase):
    """Substack mode honours limit and min_words like the other modes."""

    def test_limit_and_min_words(self):
        archive = [{"slug": "one", "post_date": "2024-03-01T00:00:00Z", "canonical_url": "https://j.substack.com/p/one"},
                   {"slug": "short", "post_date": "2024-02-01T00:00:00Z", "canonical_url": "https://j.substack.com/p/short"},
                   {"slug": "three", "post_date": "2024-01-01T00:00:00Z", "canonical_url": "https://j.substack.com/p/three"},
                   {"slug": "four", "post_date": "2023-12-01T00:00:00Z", "canonical_url": "https://j.substack.com/p/four"}]
        calls = []

        def get_json(url):
            calls.append(url)
            if "/archive" in url:
                return [] if "offset=4" in url else archive
            slug = url.rsplit("/", 1)[-1]
            body = "<p>tiny</p>" if slug == "short" else long_html()
            return {"title": slug, "body_html": body, "canonical_url": f"https://j.substack.com/p/{slug}", "audience": "everyone"}

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            stack, buf = quiet()
            with stack, mock.patch.object(scrape, "get_json", side_effect=get_json), mock.patch.object(scrape.time, "sleep"):
                scrape.scrape_substack(ws, {"name": "Jane", "substack": "j.substack.com", "limit": 2, "min_words": 150},
                                       "j.substack.com")
            urls = scrape.urls_on_disk(ws / "raw" / "jane")
        self.assertEqual(urls, {"https://j.substack.com/p/one", "https://j.substack.com/p/three"})
        self.assertIn("https://j.substack.com/p/short", buf.getvalue())
        self.assertFalse(any(u.endswith("/posts/four") for u in calls), "stopped at the limit")
        self.assertFalse(any("offset=4" in u for u in calls), "no archive page past the limit")


ATOM_XHTML = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>t</title>
<link rel="alternate" href="https://x.com/p"/>
<content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml"><p>%s</p><p>%s</p></div></content>
</entry></feed>""" % ("alpha " * 200, "beta " * 200)


class AtomXhtml(unittest.TestCase):
    """<content type="xhtml"> carries the post as child elements, not text."""

    def test_xhtml_content_is_read(self):
        html = next(scrape.feed_items(ATOM_XHTML))["html"]
        text = scrape.to_text(html)
        self.assertEqual(len(text.split()), 400)
        self.assertIn("\n", text.strip(), "paragraph break kept")


class RssLimitSemantics(unittest.TestCase):
    """limit is the number of posts on disk, in RSS mode as in sitemap mode."""

    def test_limit_counts_posts_on_disk(self):
        items = "".join(f"<item><title>t{i}</title><link>https://s.com/blog/{i}</link>"
                        f"<description><![CDATA[{long_html()}]]></description></item>" for i in range(3))
        feed = f"<rss><channel>{items}</channel></rss>".encode()
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            out = scrape.out_dir(ws, {"name": "Feed Person"})
            scrape.write_post(out, {"name": "Feed Person"}, "t9", "2024-01-01", "https://s.com/blog/9", "word " * 200)
            stack, buf = quiet()
            with stack, mock.patch.object(scrape, "fetch_bytes", return_value=feed), mock.patch.object(scrape.time, "sleep"):
                scrape.scrape_rss(ws, {"name": "Feed Person"}, {"feed": "https://s.com/feed", "limit": 2})
            self.assertEqual(len(scrape.urls_on_disk(out)), 2)
        self.assertIn("2 posts on disk", buf.getvalue())


class Utf8Reading(unittest.TestCase):
    """Pages and feeds are read as UTF-8, as in v0.3.1. One stray byte costs that byte,
    never the page or the feed. Other encodings are a known gap: GitHub issue #6."""

    def test_utf8_feed_with_one_stray_byte_keeps_its_items(self):
        feed = (b'<?xml version="1.0" encoding="utf-8"?><rss><channel><item><title>It\x92s caf\xc3\xa9</title>'
                b'<link>https://x.com/1</link><description>' + b"word " * 200 + b'</description></item></channel></rss>')
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            stack, buf = quiet()
            with stack, mock.patch.object(scrape, "fetch_bytes", return_value=feed):
                scrape.scrape_rss(ws, {"name": "Feed Person"}, {"feed": "https://x.com/feed"})
            self.assertEqual(scrape.urls_on_disk(ws / "raw" / "feed-person"), {"https://x.com/1"}, buf.getvalue())

    def save(self, page):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            with mock.patch.object(scrape, "fetch_bytes", return_value=page):
                self.assertTrue(scrape.save_page(out, {"name": "web"}, "https://x.com/p", "", 150))
            return next(out.glob("*.md")).read_text(encoding="utf-8")

    def test_utf8_page_with_one_stray_byte(self):
        text = self.save(b'<html><head><meta charset="utf-8"></head><body><main><h1>Caf\xc3\xa9</h1>'
                         + b"word " * 200 + b"It\x92s</main></body></html>")
        self.assertIn("Café", text)
        self.assertNotIn("Ã", text)

    def test_page_declared_latin1_but_sent_as_utf8(self):
        text = self.save(b'<html><head><meta charset="iso-8859-1"></head><body><main><h1>caf\xc3\xa9</h1>'
                         + b"word " * 200 + b"</main></body></html>")
        self.assertIn("café", text)
        self.assertNotIn("Ã", text)


class SubstackPaging(unittest.TestCase):
    """No archive request past the limit."""

    def run_substack(self, ws, calls):
        pages = {0: [{"slug": "one", "post_date": "2024-03-01", "canonical_url": "https://j.substack.com/p/one"},
                     {"slug": "two", "post_date": "2024-02-01", "canonical_url": "https://j.substack.com/p/two"}],
                 2: [{"slug": "three", "post_date": "2024-01-01", "canonical_url": "https://j.substack.com/p/three"}]}

        def get_json(url):
            calls.append(url)
            if "/archive" in url:
                return pages.get(int(re.search(r"offset=(\d+)", url).group(1)), [])
            slug = url.rsplit("/", 1)[-1]
            return {"title": slug, "body_html": long_html(), "canonical_url": f"https://j.substack.com/p/{slug}",
                    "audience": "everyone"}

        stack, _ = quiet()
        with stack, mock.patch.object(scrape, "get_json", side_effect=get_json), mock.patch.object(scrape.time, "sleep"):
            scrape.scrape_substack(ws, {"name": "Jane", "limit": 2}, "j.substack.com")

    def test_limit_reached_at_a_page_boundary(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            self.run_substack(Path(td), calls)
        self.assertFalse(any("offset=2" in u for u in calls), calls)

    def test_rerun_already_at_the_limit(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            self.run_substack(ws, [])
            calls = []
            self.run_substack(ws, calls)
        self.assertEqual(calls, [])


class NonUtf8RawFile(unittest.TestCase):
    """A raw/ file that isn't UTF-8 (v0.3.1 on a Windows locale, or added by hand) doesn't stop the run."""

    def test_run_continues(self):
        feed = ('<rss><channel><item><title>t</title><link>https://b.com/1</link><description>'
                + "word " * 200 + '</description></item></channel></rss>').encode()
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "sources.json").write_text(json.dumps({"authors": [
                {"name": "Ann", "site": {"kind": "rss", "feed": "https://a.com/feed"}},
                {"name": "Bob", "site": {"kind": "rss", "feed": "https://b.com/feed"}}]}))
            (ws / "raw" / "ann").mkdir(parents=True)
            (ws / "raw" / "ann" / "old.md").write_bytes(b"---\ntitle: caf\xe9\nurl: https://a.com/old\n---\n\ncaf\xe9\n")
            stack, buf = quiet()
            with stack, mock.patch.object(scrape, "fetch_bytes", return_value=feed):
                scrape.main(ws)
            self.assertIn("https://a.com/old", scrape.urls_on_disk(ws / "raw" / "ann"))
            self.assertEqual(scrape.urls_on_disk(ws / "raw" / "bob"), {"https://b.com/1"}, buf.getvalue())


class FeedEncodingValueError(unittest.TestCase):
    """Issue #6: a feed whose declared encoding the XML parser rejects (Shift_JIS,
    EUC-KR, GB2312...) raises ValueError, not ET.ParseError. main() did not catch
    ValueError, so one such feed stopped every author listed after it."""

    def test_other_authors_still_run(self):
        good_feed = ('<rss><channel><item><title>t</title><link>https://b.com/1</link><description>'
                     + "word " * 200 + '</description></item></channel></rss>').encode()
        bad_feed = ('<?xml version="1.0" encoding="Shift_JIS"?><rss><channel><item><title>t</title>'
                    '<link>https://a.jp/1</link></item></channel></rss>').encode("shift_jis")
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "sources.json").write_text(json.dumps({"authors": [
                {"name": "Jp", "site": {"kind": "rss", "feed": "https://a.jp/feed"}},
                {"name": "Bob", "site": {"kind": "rss", "feed": "https://b.com/feed"}}]}))
            stack, buf = quiet()
            with stack, mock.patch.object(scrape, "fetch_bytes",
                                          side_effect=lambda u: bad_feed if "a.jp" in u else good_feed):
                scrape.main(ws)
            self.assertEqual(scrape.urls_on_disk(ws / "raw" / "bob"), {"https://b.com/1"}, buf.getvalue())
        self.assertIn("Jp: FAILED", buf.getvalue())


class SubstackSkipRecord(unittest.TestCase):
    """A resume does not fetch teasers and short posts again; a lower min_words does."""

    ARCHIVE = [{"slug": s, "post_date": "2024-01-01", "canonical_url": f"https://j.substack.com/p/{s}"}
               for s in ("long", "teaser", "short")]

    def run_once(self, ws, min_words=150):
        calls = []

        def get_json(url):
            calls.append(url)
            if "/archive" in url:
                return self.ARCHIVE if "offset=0" in url else []
            slug = url.rsplit("/", 1)[-1]
            body = {"long": long_html(), "teaser": "<p>" + "word " * 40 + "</p>", "short": "<p>tiny</p>"}[slug]
            return {"title": slug, "body_html": body, "canonical_url": f"https://j.substack.com/p/{slug}",
                    "audience": "only_paid" if slug == "teaser" else "everyone"}

        stack, buf = quiet()
        with stack, mock.patch.object(scrape, "get_json", side_effect=get_json), mock.patch.object(scrape.time, "sleep"):
            scrape.scrape_substack(ws, {"name": "Jane", "min_words": min_words}, "j.substack.com")
        return [u for u in calls if "/posts/" in u], buf.getvalue()

    def test_resume_skips_what_was_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            first, out1 = self.run_once(ws)
            second, out2 = self.run_once(ws)
            self.assertEqual(len(first), 3)
            self.assertIn("paywalled teaser (40 words)", out1)
            self.assertEqual(second, [])
            self.assertIn("2 skipped on an earlier run", out2)
            self.assertEqual([p.name for p in (ws / "raw" / "jane").glob("*.md")], ["2024-01-01-long.md"])

    def test_lower_min_words_fetches_them_again(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            self.run_once(ws)
            again, _ = self.run_once(ws, min_words=30)
            self.assertEqual(again, ["https://j.substack.com/api/v1/posts/teaser"])
            self.assertIn("https://j.substack.com/p/teaser", scrape.urls_on_disk(ws / "raw" / "jane"))


if __name__ == "__main__":
    unittest.main()
