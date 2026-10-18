#!/usr/bin/env python3
"""
Render CMS-authored Markdown news posts into styled HTML pages that match the
BalticDryIndex.com chrome, plus a /news/ index. Lets the static site have an
easy CMS: the editor (Sveltia) commits Markdown to content/news/*.md, this
script turns each into /news/<slug>/index.html.

Run from the repo root:  python scripts/build_news.py
Needs:  pip install markdown pyyaml

Each post file content/news/<slug>.md looks like:

    ---
    title: Capesize rates jump on iron ore demand
    date: 2026-10-18
    description: A short summary for search engines and the news index.
    author: BalticDryIndex.com
    ---
    Body in **Markdown**. Normal paragraphs, headings, lists, links.
"""
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

try:
    import yaml
    import markdown as md
except ImportError:
    print("Missing deps. Run: pip install markdown pyyaml", file=sys.stderr)
    raise

ROOT        = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "news"
NEWS_DIR    = ROOT / "news"
SITE_URL    = "https://www.balticdryindex.com"

HEADER = """<header>
  <div class="header-inner">
    <a href="/" class="logo"><span class="logo-main">BALTIC DRY</span><span class="logo-dot">.</span><span class="logo-tag">INDEX</span></a>
    <nav>
      <a href="/">Live Data</a>
      <a href="/what-is-the-baltic-dry-index/">About BDI</a>
      <a href="/bdi-chart-historical-data/">Chart</a>
      <a href="/vessel-classes/">Vessels</a>
      <a href="/shipping-stocks/">Stocks</a>
      <a href="/analysis/">Analysis</a>
      <a href="/news/" class="active">News</a>
      <a href="/tools/">Tools</a>
      <a href="/" class="nav-cta">Free Alerts</a>
    </nav>
  </div>
</header>"""

FOOTER = """<footer>
  <div class="footer-inner">
    <div><a href="/" class="logo"><span class="logo-main">BALTIC DRY</span><span class="logo-dot">.</span></a><div class="footer-tagline">The independent source for Baltic Dry Index data, shipping market analysis, and freight rate intelligence.</div></div>
    <div><div class="footer-col-title">Data</div><ul class="footer-links"><li><a href="/">Live BDI Chart</a></li><li><a href="/bdi-chart-historical-data/">Historical Data</a></li><li><a href="/news/">News</a></li><li><a href="/analysis/">Analysis</a></li></ul></div>
    <div><div class="footer-col-title">Tools</div><ul class="footer-links"><li><a href="/tce-calculator/">TCE Calculator</a></li><li><a href="/voyage-calculator/">Voyage Estimator</a></li><li><a href="/freight-rate-calculator/">Freight Cost</a></li><li><a href="/api/">Data API</a></li></ul></div>
    <div><div class="footer-col-title">Company</div><ul class="footer-links"><li><a href="/about/">About</a></li><li><a href="/contact/">Contact</a></li><li><a href="/privacy-policy/">Privacy Policy</a></li><li><a href="/disclaimer/">Disclaimer</a></li></ul></div>
  </div>
  <div class="footer-bottom"><div class="footer-copy">© 2026 Virtual Random LLC · BalticDryIndex.com</div><div class="footer-disclaimer">Not financial advice. Estimates only.</div></div>
</footer>"""

PROSE_STYLE = """<style>
.news-main{max-width:820px;margin:0 auto;padding:24px 20px 72px;}
.news-main h1{font-family:var(--display);font-size:clamp(28px,4.5vw,46px);color:#fff;letter-spacing:.02em;line-height:1.1;margin:.1em 0 .3em;}
.news-meta{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--gold);margin-bottom:22px;}
.breadcrumb{max-width:820px;margin:0 auto;padding:16px 20px 0;font-family:var(--mono);font-size:11px;color:var(--text-muted);}
.breadcrumb a{color:var(--text-dim);text-decoration:none;}.breadcrumb span{margin:0 8px;}
.news-card{display:block;background:var(--surface);border:1px solid var(--border);padding:20px 22px;text-decoration:none;margin-bottom:2px;transition:border-color .2s;}
.news-card:hover{border-color:var(--border2);}
.news-card .nc-date{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--gold);}
.news-card .nc-title{font-size:18px;font-weight:600;color:var(--text);line-height:1.35;margin:7px 0;}
.news-card .nc-desc{font-size:13px;color:var(--text-dim);line-height:1.6;}
</style>"""

def page(title, description, canonical, body, extra_head=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:type" content="article">
<meta property="og:url" content="{canonical}">
<meta name="theme-color" content="#090b0e">
<link rel="stylesheet" href="/assets/style.css">
{PROSE_STYLE}{extra_head}
</head>
<body>
{HEADER}
{body}
{FOOTER}
</body>
</html>"""

def parse_post(path):
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.DOTALL)
    if not m:
        front, body_md = {}, raw
    else:
        front = yaml.safe_load(m.group(1)) or {}
        body_md = m.group(2)
    slug = front.get("slug") or path.stem
    title = front.get("title", slug.replace("-", " ").title())
    date = str(front.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")))[:10]
    desc = front.get("description", "")
    author = front.get("author", "BalticDryIndex.com")
    body_html = md.markdown(body_md, extensions=["extra", "sane_lists"])
    return {"slug": slug, "title": title, "date": date, "desc": desc,
            "author": author, "body": body_html}

def render_post(p):
    try:
        dt = datetime.strptime(p["date"], "%Y-%m-%d")
        date_disp = dt.strftime("%-d %B %Y")
    except ValueError:
        date_disp = p["date"]
    canon = f"{SITE_URL}/news/{p['slug']}/"
    schema = (
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"NewsArticle",'
        f'"headline":{_j(p["title"])},"datePublished":"{p["date"]}T12:00:00Z",'
        f'"dateModified":"{p["date"]}T12:00:00Z","description":{_j(p["desc"])},'
        f'"url":"{canon}","mainEntityOfPage":"{canon}",'
        '"publisher":{"@type":"Organization","name":"BalticDryIndex.com",'
        f'"url":"{SITE_URL}"}},"author":{{"@type":"Organization","name":{_j(p["author"])}}}}}'
        '</script>'
    )
    body = f"""<div class="breadcrumb"><a href="/">Home</a><span>›</span><a href="/news/">News</a><span>›</span>{date_disp}</div>
<main class="news-main">
  <h1>{p['title']}</h1>
  <div class="news-meta">{date_disp} · {p['author']}</div>
  <article class="prose">
{p['body']}
  <p style="font-family:var(--mono);font-size:10px;color:var(--text-muted);margin-top:28px;padding-top:14px;border-top:1px solid var(--border);">Published by BalticDryIndex.com · Not financial advice. <a href="/disclaimer/">Disclaimer</a></p>
  </article>
</main>"""
    html = page(f"{p['title']} | BalticDryIndex.com", p["desc"], canon, body, extra_head=schema)
    out = NEWS_DIR / p["slug"] / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out

def render_index(posts):
    cards = []
    for p in posts:
        try:
            date_disp = datetime.strptime(p["date"], "%Y-%m-%d").strftime("%-d %b %Y")
        except ValueError:
            date_disp = p["date"]
        cards.append(
            f'<a class="news-card" href="/news/{p["slug"]}/">'
            f'<div class="nc-date">{date_disp}</div>'
            f'<div class="nc-title">{p["title"]}</div>'
            f'<div class="nc-desc">{p["desc"]}</div></a>'
        )
    body = f"""<div class="breadcrumb"><a href="/">Home</a><span>›</span>News</div>
<main class="news-main">
  <h1>Shipping &amp; BDI News</h1>
  <div class="news-meta">Dry bulk market news and commentary</div>
  {''.join(cards) if cards else '<p style="color:var(--text-dim);">No posts yet.</p>'}
</main>"""
    html = page("Shipping & BDI News | BalticDryIndex.com",
                "Latest dry bulk shipping and Baltic Dry Index news and commentary from BalticDryIndex.com.",
                f"{SITE_URL}/news/", body)
    (NEWS_DIR / "index.html").write_text(html, encoding="utf-8")

def _j(s):
    import json
    return json.dumps(s or "", ensure_ascii=False)

def main():
    if not CONTENT_DIR.exists():
        print(f"No content dir at {CONTENT_DIR}; nothing to build.")
        CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    posts = [parse_post(p) for p in CONTENT_DIR.glob("*.md")]
    posts.sort(key=lambda x: x["date"], reverse=True)
    for p in posts:
        out = render_post(p)
        print("OK", out.relative_to(ROOT))
    render_index(posts)
    print(f"OK news/index.html ({len(posts)} posts)")

if __name__ == "__main__":
    main()
