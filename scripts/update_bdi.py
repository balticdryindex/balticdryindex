#!/usr/bin/env python3
"""
BalticDryIndex.com Update Script

TWO MODES — called by two separate GitHub Actions workflows:

  python scripts/update_bdi.py --data-only
    Called by daily-data.yml (Mon–Fri 14:00 UTC)
    - Fetches BDI from Baltic Exchange API
    - Saves data/latest.json
    - Pushes latest.json to gh-pages branch ONLY
    - Netlify never sees this commit → zero Netlify credits burned

  python scripts/update_bdi.py
    Called by weekly-news.yml (Sunday 12:00 UTC)
    - Fetches BDI from Baltic Exchange API
    - Saves data/latest.json
    - Pre-renders live BDI into index.html (SEO)
    - Generates weekly analysis article in /analysis/
    - Updates /analysis/index.html with new card
    - Updates sitemap.xml
    - Generates /feed.xml RSS
    - Removes /news/ folder (consolidated into /analysis/)
    - Removes Chart.js from non-chart pages (Core Web Vitals)
    - Commits everything to main → triggers ONE Netlify deploy
    - ~4 deploys/month × 15 credits = 60 credits (well within 300 free limit)
"""

import datetime
import json
import re
import sys
import shutil
from pathlib import Path
import requests

ROOT         = Path(__file__).parent.parent
DATA_FILE    = ROOT / "data" / "latest.json"
ANALYSIS_DIR = ROOT / "analysis"
SITEMAP_FILE = ROOT / "sitemap.xml"
FEED_FILE    = ROOT / "feed.xml"
INDEX_FILE   = ROOT / "index.html"
SITE_URL     = "https://www.balticdryindex.com"

DATA_ONLY = "--data-only" in sys.argv

# ── HELPERS ───────────────────────────────────────────────────────────────────

def fmt(n):
    return f"{int(round(n)):,}"

def sgn(n):
    return "+" if n >= 0 else ""

def load_previous():
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except Exception:
        return None

def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print("OK data/latest.json")

def build_index(cur, prev):
    chg = cur - prev
    pct = round((chg / prev) * 100, 2) if prev else 0
    return {"value": cur, "prev": prev, "change": chg, "pct": pct}

# ── 1. FETCH DATA ─────────────────────────────────────────────────────────────

def fetch_api():
    try:
        r = requests.get(
            "https://blacksun-api.balticexchange.com/api/ticker",
            timeout=10
        )
        if r.status_code != 200:
            return None
        result = {}
        for item in r.json():
            code = item.get("indexDataSetName", "").lower()
            cur  = item.get("current")
            if cur and cur.get("value") is not None:
                result[code] = {
                    "value": int(cur["value"]),
                    "date":  cur["indexDate"][:10]
                }
        if "bdi" in result:
            print(f"API BDI={result['bdi']['value']} date={result['bdi']['date']}")
            return result
        return None
    except Exception as e:
        print("API ERROR:", e)
        return None

def fetch_all_data():
    prev = load_previous()
    if not prev:
        print("No previous data found.")
        return None

    api = fetch_api()
    if not api:
        print("API failed — no update.")
        return None

    def safe(k):
        if k in api:
            return build_index(api[k]["value"], prev[k]["value"])
        return prev[k]

    return {
        "date":    api["bdi"]["date"],
        "updated": datetime.datetime.utcnow().strftime("%H:%M UTC"),
        "source":  "Baltic Exchange",
        "bdi":  safe("bdi"),
        "bci":  safe("bci"),
        "bpi":  safe("bpi"),
        "bsi":  safe("bsi"),
        "bhsi": safe("bhsi"),
        "stats": prev.get("stats", {}),
    }

# ── 2. PRE-RENDER HOMEPAGE (SEO — weekly only) ────────────────────────────────

def prerender_homepage(data):
    """Bake real BDI values + Dataset schema into index.html for Google."""
    if not INDEX_FILE.exists():
        return
    html = INDEX_FILE.read_text(encoding="utf-8")
    bdi  = data["bdi"]
    arrow = "▲" if bdi["change"] >= 0 else "▼"
    s     = sgn(bdi["change"])
    cls   = "up" if bdi["change"] >= 0 else "dn"
    dt    = datetime.datetime.strptime(data["date"], "%Y-%m-%d")
    date_display = dt.strftime("%-d %b %Y")

    # Replace spinner with real value
    html = re.sub(
        r'(<div[^>]+id="bdi-val"[^>]*>).*?(</div>)',
        rf'\g<1>{fmt(bdi["value"])}\g<2>',
        html, flags=re.DOTALL
    )
    # Replace loading text with real change
    html = re.sub(
        r'(<div[^>]+id="bdi-change"[^>]*)[^>]*>.*?(</div>)',
        rf'\g<1> class="bdi-change {cls}">{arrow} {s}{fmt(bdi["change"])} pts  {s}{bdi["pct"]:.2f}%\g<2>',
        html, flags=re.DOTALL
    )
    # Replace timestamp
    html = re.sub(
        r'(<div[^>]+id="bdi-ts"[^>]*>).*?(</div>)',
        rf'\g<1>{date_display} · Baltic Exchange\g<2>',
        html, flags=re.DOTALL
    )

    # Upsert Dataset schema
    dataset = (
        '{"@context":"https://schema.org","@type":"Dataset",'
        f'"name":"Baltic Dry Index Daily Value",'
        f'"description":"BDI as published by the Baltic Exchange. '
        f'Current value: {fmt(bdi["value"])} as of {data["date"]}.",'
        f'"url":"{SITE_URL}/",'
        '"provider":{"@type":"Organization","name":"Baltic Exchange",'
        '"url":"https://www.balticexchange.com"},'
        f'"temporalCoverage":"1985/{data["date"]}",'
        f'"variableMeasured":{{"@type":"PropertyValue",'
        f'"name":"Baltic Dry Index","value":{bdi["value"]},'
        f'"unitText":"index points","valueReference":"{data["date"]}"}}'
        "}"
    )
    if '"@type":"Dataset"' in html.replace(" ", ""):
        html = re.sub(
            r'\{[^{}]*"@type"\s*:\s*"Dataset"[^{}]*\}',
            dataset, html, flags=re.DOTALL
        )
    else:
        html = html.replace(
            '</script>\n  <link rel="icon"',
            f'</script>\n<script type="application/ld+json">\n{dataset}\n</script>\n  <link rel="icon"'
        )

    INDEX_FILE.write_text(html, encoding="utf-8")
    print(f"OK index.html pre-rendered BDI={fmt(bdi['value'])}")

# ── 3. GENERATE ANALYSIS ARTICLE (weekly only) ────────────────────────────────

def generate_article(data):
    bdi  = data["bdi"]; bci = data["bci"]
    bpi  = data["bpi"]; bsi = data["bsi"]; bhsi = data["bhsi"]
    dt   = datetime.datetime.strptime(data["date"], "%Y-%m-%d")
    date_display = dt.strftime("%-d %B %Y")
    weekday = dt.strftime("%A")

    movers = [
        ("Capesize", bci), ("Panamax", bpi),
        ("Supramax", bsi), ("Handysize", bhsi)
    ]
    top_name, top_idx = max(movers, key=lambda x: abs(x[1]["pct"]))
    direction = "rises" if bdi["change"] >= 0 else "falls"
    Dir = direction.capitalize()
    abs_chg = abs(bdi["change"])
    abs_pct = abs(bdi["pct"])

    if abs_pct >= 3:
        headline = f"Baltic Dry Index {Dir} Sharply to {fmt(bdi['value'])} as {top_name} Demand Surges"
    elif abs_pct >= 1.5:
        headline = f"BDI {Dir} {abs_pct:.1f}% to {fmt(bdi['value'])} — {top_name} Leads"
    elif bdi["change"] == 0:
        headline = f"Baltic Dry Index Holds Steady at {fmt(bdi['value'])} on {date_display}"
    else:
        headline = f"Baltic Dry Index {Dir} to {fmt(bdi['value'])} on {date_display}"

    arrow = "▲" if bdi["change"] >= 0 else "▼"
    s     = sgn(bdi["change"])
    cls   = "up" if bdi["change"] >= 0 else "dn"

    # Opening context
    if bdi["change"] > 50:
        ctx = "Strong demand across the dry bulk market pushed rates higher, with cargo volumes outpacing available tonnage on key routes."
    elif bdi["change"] > 0:
        ctx = "Moderate improvements in freight demand supported a modest advance in dry bulk rates."
    elif bdi["change"] < -50:
        ctx = "Softening cargo demand and elevated vessel availability weighed on dry bulk rates across most vessel classes."
    elif bdi["change"] < 0:
        ctx = "Reduced cargo inquiry and a well-supplied vessel list contributed to a modest retreat in the index."
    else:
        ctx = "Demand and tonnage availability remained broadly balanced on the major dry bulk trading routes."

    p1 = (
        f"The <strong>Baltic Dry Index (BDI)</strong> {direction}d {abs_chg} points "
        f"({s}{bdi['pct']:.2f}%) to <strong>{fmt(bdi['value'])}</strong> on {weekday}, "
        f"{date_display}, according to the London-based Baltic Exchange. {ctx}"
    )

    # Capesize
    if bci["change"] > 150:
        p_cape = (
            f"The <strong>Capesize index</strong> jumped {fmt(bci['change'])} points "
            f"({sgn(bci['change'])}{bci['pct']:.2f}%) to {fmt(bci['value'])} on strong iron ore "
            f"demand on the Brazil-China C3 corridor and improved Vale export volumes."
        )
    elif bci["change"] > 0:
        p_cape = (
            f"The <strong>Capesize index</strong> edged {fmt(bci['change'])} points higher to "
            f"{fmt(bci['value'])}, supported by steady iron ore demand on the Australia and "
            f"Brazil corridors to China."
        )
    elif bci["change"] < -150:
        p_cape = (
            f"The <strong>Capesize index</strong> fell {fmt(abs(bci['change']))} points to "
            f"{fmt(bci['value'])} as iron ore cargo volumes softened and Atlantic vessel "
            f"availability increased."
        )
    else:
        p_cape = (
            f"The <strong>Capesize index</strong> moved {sgn(bci['change'])}"
            f"{fmt(bci['change'])} points to {fmt(bci['value'])}, reflecting broadly "
            f"balanced conditions on iron ore corridors."
        )

    # Panamax
    if bpi["change"] > 0:
        p_pana = (
            f"The <strong>Panamax index</strong> gained {fmt(bpi['change'])} points to "
            f"{fmt(bpi['value'])}, benefiting from improved grain volumes in the US Gulf "
            f"and Atlantic coal demand."
        )
    elif bpi["change"] < 0:
        p_pana = (
            f"The <strong>Panamax index</strong> slipped {fmt(abs(bpi['change']))} points "
            f"to {fmt(bpi['value'])} as Atlantic grain volumes remained subdued."
        )
    else:
        p_pana = f"The <strong>Panamax index</strong> held steady at {fmt(bpi['value'])}."

    # Minor bulkers
    supra_dir = "advanced" if bsi["change"] >= 0 else "retreated"
    handy_dir = "edged higher" if bhsi["change"] >= 0 else "eased"
    p_minor = (
        f"The <strong>Supramax index</strong> {supra_dir} {fmt(abs(bsi['change']))} points "
        f"to {fmt(bsi['value'])}, while the <strong>Handysize index</strong> {handy_dir} "
        f"to {fmt(bhsi['value'])}."
    )

    # Signal
    val = bdi["value"]
    if val > 3000:
        p_signal = (
            f"At {fmt(val)}, the BDI is in historically healthy territory, typically "
            f"associated with robust global commodity trade and strong earnings across "
            f"all dry bulk vessel classes."
        )
    elif val > 2000:
        p_signal = (
            f"At {fmt(val)}, the BDI remains in moderately positive territory. "
            f"Capesize earnings remain above breakeven for most modern vessels, "
            f"though significant upside requires sustained demand growth from "
            f"Chinese iron ore and grain importers."
        )
    elif val > 1500:
        p_signal = (
            f"The BDI at {fmt(val)} reflects a market in recovery mode, with rates "
            f"above breakeven for modern vessels but requiring a meaningful demand "
            f"pickup for a sustained rally."
        )
    else:
        p_signal = (
            f"With the BDI at {fmt(val)}, the market is under pressure. Rates at "
            f"this level may strain profitability for older vessels and could signal "
            f"softening in global commodity trade flows."
        )

    slug     = f"bdi-{data['date']}"
    url_path = f"/analysis/{slug}/"
    canon    = f"{SITE_URL}{url_path}"
    meta_desc = (
        f"Baltic Dry Index {direction}s {abs_chg} points to {fmt(bdi['value'])} "
        f"on {date_display}. BCI {fmt(bci['value'])}, BPI {fmt(bpi['value'])}, "
        f"BSI {fmt(bsi['value'])}. Daily shipping market analysis."
    )
    excerpt = (
        f"The BDI {'rose' if bdi['change']>=0 else 'fell'} {abs_chg} points "
        f"({s}{bdi['pct']:.2f}%) to {fmt(bdi['value'])} on {date_display}. "
        f"BCI {fmt(bci['value'])}, BPI {fmt(bpi['value'])}, BSI {fmt(bsi['value'])}."
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{headline} | BalticDryIndex.com</title>
<meta name="description" content="{meta_desc}">
<link rel="canonical" href="{canon}">
<meta property="og:title" content="{headline}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:type" content="article">
<meta property="og:url" content="{canon}">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<meta name="theme-color" content="#090b0e">
<link rel="stylesheet" href="/assets/style.css">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"NewsArticle",
"headline":"{headline}",
"datePublished":"{data['date']}T14:00:00Z",
"dateModified":"{data['date']}T14:00:00Z",
"description":"{meta_desc}",
"url":"{canon}",
"mainEntityOfPage":"{canon}",
"publisher":{{"@type":"Organization","name":"BalticDryIndex.com",
"url":"{SITE_URL}","logo":{{"@type":"ImageObject","url":"{SITE_URL}/favicon-192.png"}}}},
"about":{{"@type":"FinancialProduct","name":"Baltic Dry Index","alternateName":"BDI"}},
"mentions":[
  {{"@type":"QuantitativeValue","name":"BDI","value":{bdi['value']},"unitText":"index points"}},
  {{"@type":"QuantitativeValue","name":"BCI","value":{bci['value']},"unitText":"index points"}},
  {{"@type":"QuantitativeValue","name":"BPI","value":{bpi['value']},"unitText":"index points"}},
  {{"@type":"QuantitativeValue","name":"BSI","value":{bsi['value']},"unitText":"index points"}}
]}}
</script>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9696700979125307" crossorigin="anonymous"></script>
</head>
<body>
<div class="ticker-bar"><div class="ticker-label">LIVE</div>
<div class="ticker-overflow"><div class="ticker-track" id="tickerTrack">
<div class="ticker-item"><span class="t-name">BDI</span><span class="t-val">{fmt(bdi['value'])}</span><span class="{cls}">{arrow} {s}{fmt(bdi['change'])}</span></div>
<div class="ticker-item"><span class="t-name">BCI</span><span class="t-val">{fmt(bci['value'])}</span><span class="{'up' if bci['change']>=0 else 'dn'}">{sgn(bci['change'])}{fmt(bci['change'])}</span></div>
<div class="ticker-item"><span class="t-name">BPI</span><span class="t-val">{fmt(bpi['value'])}</span><span class="{'up' if bpi['change']>=0 else 'dn'}">{sgn(bpi['change'])}{fmt(bpi['change'])}</span></div>
<div class="ticker-item"><span class="t-name">BSI</span><span class="t-val">{fmt(bsi['value'])}</span><span class="{'up' if bsi['change']>=0 else 'dn'}">{sgn(bsi['change'])}{fmt(bsi['change'])}</span></div>
</div></div></div>
<header><div class="header-inner">
<a href="/" class="logo"><span class="logo-main">BALTIC DRY</span><span class="logo-dot">.</span><span class="logo-tag">INDEX</span></a>
<nav>
<a href="/">Live Data</a>
<a href="/what-is-the-baltic-dry-index/">About BDI</a>
<a href="/bdi-chart-historical-data/">Chart</a>
<a href="/vessel-classes/">Vessels</a>
<a href="/shipping-stocks/">Stocks</a>
<a href="/analysis/" class="active">Analysis</a>
<a href="/glossary/">Glossary</a>
<a href="/tools/">Tools</a>
<a href="/" class="nav-cta">Free Alerts</a>
</nav>
<div class="lang-switcher">
<a href="/analysis/" class="active">EN</a>
<a href="/zh/analysis/">中文</a><a href="/ja/analysis/">日本語</a>
<a href="/es/analysis/">ES</a><a href="/fr/analysis/">FR</a>
<a href="/ar/analysis/">AR</a><a href="/pt/analysis/">PT</a>
<a href="/ru/analysis/">RU</a>
</div>
</div></header>

<div class="breadcrumb"><a href="/">Home</a><span>›</span><a href="/analysis/">Analysis</a><span>›</span>{date_display}</div>

<div style="max-width:860px;margin:0 auto;padding:32px 24px 0;position:relative;z-index:1;">
<div style="font-family:var(--mono);font-size:10px;letter-spacing:.2em;color:var(--gold);text-transform:uppercase;margin-bottom:10px;">Weekly Market Wrap · {date_display}</div>
<h1 style="font-family:'Bebas Neue',sans-serif;font-size:clamp(28px,4vw,48px);color:#fff;letter-spacing:.02em;line-height:1.1;margin-bottom:16px;">{headline}</h1>

<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:2px;margin:24px 0;">
<div class="stat-box"><div class="stat-value {cls}" style="font-size:26px;">{fmt(bdi['value'])}</div><div class="stat-label">BDI</div><div class="stat-change {cls}">{arrow}{s}{fmt(bdi['change'])}</div></div>
<div class="stat-box"><div class="stat-value" style="font-size:22px;">{fmt(bci['value'])}</div><div class="stat-label">BCI</div><div class="stat-change {'up' if bci['change']>=0 else 'dn'}">{sgn(bci['change'])}{fmt(bci['change'])}</div></div>
<div class="stat-box"><div class="stat-value" style="font-size:22px;">{fmt(bpi['value'])}</div><div class="stat-label">BPI</div><div class="stat-change {'up' if bpi['change']>=0 else 'dn'}">{sgn(bpi['change'])}{fmt(bpi['change'])}</div></div>
<div class="stat-box"><div class="stat-value" style="font-size:22px;">{fmt(bsi['value'])}</div><div class="stat-label">BSI</div><div class="stat-change {'up' if bsi['change']>=0 else 'dn'}">{sgn(bsi['change'])}{fmt(bsi['change'])}</div></div>
<div class="stat-box"><div class="stat-value" style="font-size:22px;">{fmt(bhsi['value'])}</div><div class="stat-label">BHSI</div><div class="stat-change {'up' if bhsi['change']>=0 else 'dn'}">{sgn(bhsi['change'])}{fmt(bhsi['change'])}</div></div>
</div>

<div style="margin:20px 0;text-align:center;"><ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-9696700979125307" data-ad-slot="auto" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></div>

<article class="prose">
<p>{p1}</p>
<h2>Capesize Rates</h2><p>{p_cape}</p>
<h2>Panamax &amp; Smaller Vessels</h2><p>{p_pana}</p><p>{p_minor}</p>
<h2>What the BDI Signals</h2><p>{p_signal}</p>
<p>The BDI is published daily by the <a href="https://www.balticexchange.com" target="_blank" rel="noopener">Baltic Exchange</a> at approximately 13:00 GMT each working day.</p>
<h2>Track the BDI Daily</h2>
<p>Follow the Baltic Dry Index on <a href="/">BalticDryIndex.com</a> — including <a href="/bdi-chart-historical-data/">interactive historical charts</a>, <a href="/vessel-classes/">vessel class guides</a>, <a href="/tools/">shipping calculators</a> and <a href="/analysis/">weekly market analysis</a>.</p>
<p style="font-family:var(--mono);font-size:10px;color:var(--text-muted);margin-top:24px;padding-top:14px;border-top:1px solid var(--border);">Source: Baltic Exchange · {date_display} · Data indicative only, not financial advice. <a href="/disclaimer/">Disclaimer</a></p>
</article>

<div style="margin:24px 0;text-align:center;"><ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-9696700979125307" data-ad-slot="auto" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></div>

<div class="broker-strip">
<div class="broker-label">Trade Shipping Stocks &amp; Commodities — Partner Brokers</div>
<div class="broker-grid" style="grid-template-columns:1fr 1fr;">
<a href="https://ibkr.com/referral/julio411" class="broker-card" target="_blank" rel="noopener sponsored"><div class="broker-name">IBKR</div><div class="broker-desc">Low-cost access to global markets. Trade SBLK, GOGL and all dry bulk shipping stocks.</div><div class="broker-cta">Open Account →</div></a>
<a href="https://dukascopy.bank/swiss/open-mca-account/?ref=YJM-PUE&lang=en" class="broker-card" target="_blank" rel="noopener sponsored"><div class="broker-name">Dukascopy</div><div class="broker-desc">Swiss regulated bank and broker. Trade commodities and global markets professionally.</div><div class="broker-cta">Open Account →</div></a>
</div></div>
</div>

<footer><div class="footer-inner">
<div><a href="/" class="logo"><span class="logo-main">BALTIC DRY</span><span class="logo-dot">.</span></a><div class="footer-tagline">The independent source for Baltic Dry Index data, shipping market analysis, and freight rate intelligence. Updated daily.</div></div>
<div><div class="footer-col-title">Data</div><ul class="footer-links"><li><a href="/">Live BDI Chart</a></li><li><a href="/bdi-chart-historical-data/">Historical Data</a></li><li><a href="/vessel-classes/">Vessel Classes</a></li><li><a href="/shipping-stocks/">Shipping Stocks</a></li></ul></div>
<div><div class="footer-col-title">Learn</div><ul class="footer-links"><li><a href="/what-is-the-baltic-dry-index/">What is the BDI?</a></li><li><a href="/analysis/">Analysis</a></li><li><a href="/glossary/">Glossary</a></li><li><a href="/tools/">Tools</a></li></ul></div>
<div><div class="footer-col-title">Languages</div><ul class="footer-links"><li><a href="/">English</a></li><li><a href="/zh/">中文</a></li><li><a href="/ja/">日本語</a></li><li><a href="/es/">Español</a></li><li><a href="/fr/">Français</a></li><li><a href="/ar/">العربية</a></li><li><a href="/pt/">Português</a></li><li><a href="/ru/">Русский</a></li></ul></div>
</div>
<div class="footer-bottom"><div class="footer-copy">© 2026 Sea Blast LTD · BalticDryIndex.com</div><div class="footer-disclaimer">Data indicative only. Not financial advice. <a href="/disclaimer/" style="color:var(--text-muted);">Disclaimer</a></div></div>
</footer>
<script src="/assets/bdi.js"></script>
<script>BDI.load(function(d){{BDI.buildTicker(d);}});</script>
</body></html>"""

    return slug, url_path, headline, excerpt, html

# ── 4. SAVE ARTICLE ───────────────────────────────────────────────────────────

def save_article(slug, html):
    d = ANALYSIS_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html, encoding="utf-8")
    print(f"OK analysis/{slug}/index.html")

# ── 5. UPDATE ANALYSIS INDEX ──────────────────────────────────────────────────

def update_analysis_index(slug, url_path, headline, excerpt, date_str):
    idx = ANALYSIS_DIR / "index.html"
    if not idx.exists():
        return
    html = idx.read_text(encoding="utf-8")
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    date_short = dt.strftime("%-d %b %Y")

    card = (
        f'      <a href="{url_path}" style="background:var(--surface);border:1px solid var(--border);'
        f'padding:22px;text-decoration:none;display:block;transition:border-color .2s;" '
        f'onmouseover="this.style.borderColor=\'var(--border2)\'" '
        f'onmouseout="this.style.borderColor=\'var(--border)\'">\n'
        f'        <div class="article-category">Weekly Wrap · {date_short}</div>\n'
        f'        <div class="article-title" style="font-size:17px;font-weight:500;'
        f'color:var(--text);line-height:1.35;margin:8px 0;">{headline}</div>\n'
        f'        <p style="font-size:13px;color:var(--text-dim);line-height:1.6;">{excerpt}</p>\n'
        f'        <div class="article-meta" style="margin-top:10px;">BDI Analysis · 3 min read</div>\n'
        f'      </a>'
    )

    # Insert after <!-- ARTICLE LIST --> marker
    marker    = "<!-- ARTICLE LIST -->"
    open_grid = '<div style="display:grid;gap:2px;">'
    if marker in html and open_grid in html:
        pos = html.find(open_grid, html.find(marker)) + len(open_grid)
        html = html[:pos] + "\n" + card + html[pos:]
    else:
        html = html.replace(
            '<a href="#" style="background:var(--surface)',
            card + '\n      <a href="#" style="background:var(--surface)', 1
        )

    idx.write_text(html, encoding="utf-8")
    print("OK analysis/index.html updated")


# ── 6. SITEMAP ────────────────────────────────────────────────────────────────

def update_sitemap(url_path, date_str):
    try:
        sm = SITEMAP_FILE.read_text(encoding="utf-8")
    except Exception:
        sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n</urlset>'

    full = f"{SITE_URL}{url_path}"
    if full not in sm:
        entry = (
            f'  <url><loc>{full}</loc>'
            f'<changefreq>monthly</changefreq>'
            f'<priority>0.75</priority>'
            f'<lastmod>{date_str}</lastmod></url>'
        )
        sm = sm.replace("</urlset>", entry + "\n</urlset>")

    # Update homepage and analysis lastmod
    sm = re.sub(
        r'(<loc>https://www\.balticdryindex\.com/</loc>.*?<lastmod>)[^<]*(</lastmod>)',
        rf'\g<1>{date_str}\g<2>', sm, flags=re.DOTALL
    )
    sm = re.sub(
        r'(<loc>https://www\.balticdryindex\.com/analysis/</loc>.*?<lastmod>)[^<]*(</lastmod>)',
        rf'\g<1>{date_str}\g<2>', sm, flags=re.DOTALL
    )

    SITEMAP_FILE.write_text(sm, encoding="utf-8")
    print(f"OK sitemap.xml → {url_path}")

# ── 7. RSS FEED ───────────────────────────────────────────────────────────────

def generate_rss():
    articles = []
    if ANALYSIS_DIR.exists():
        for d in sorted(ANALYSIS_DIR.iterdir(), reverse=True):
            if not d.is_dir() or not d.name.startswith("bdi-"):
                continue
            p = d / "index.html"
            if not p.exists():
                continue
            html = p.read_text(encoding="utf-8")
            tm  = re.search(r"<title>(.*?)\s*\|", html)
            dm  = re.search(r'<meta name="description" content="([^"]*)"', html)
            dtm = re.search(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})', html)
            if tm and dtm:
                pub = datetime.datetime.strptime(dtm.group(1), "%Y-%m-%d")
                articles.append({
                    "title": tm.group(1),
                    "desc":  dm.group(1) if dm else "",
                    "url":   f"{SITE_URL}/analysis/{d.name}/",
                    "date":  pub.strftime("%a, %d %b %Y 14:00:00 +0000"),
                })
            if len(articles) >= 20:
                break

    now = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = "".join(
        f"  <item>\n"
        f"    <title><![CDATA[{a['title']}]]></title>\n"
        f"    <link>{a['url']}</link>\n"
        f"    <guid isPermaLink=\"true\">{a['url']}</guid>\n"
        f"    <description><![CDATA[{a['desc']}]]></description>\n"
        f"    <pubDate>{a['date']}</pubDate>\n"
        f"  </item>\n"
        for a in articles
    )
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '<channel>\n'
        '  <title>Baltic Dry Index Analysis — BalticDryIndex.com</title>\n'
        f'  <link>{SITE_URL}/analysis/</link>\n'
        '  <description>Weekly BDI market analysis and shipping freight intelligence.</description>\n'
        '  <language>en-gb</language>\n'
        f'  <lastBuildDate>{now}</lastBuildDate>\n'
        f'  <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>\n'
        f'{items}'
        '</channel>\n</rss>'
    )
    FEED_FILE.write_text(feed, encoding="utf-8")
    print(f"OK feed.xml ({len(articles)} articles)")

# ── 8. REMOVE /news/ ──────────────────────────────────────────────────────────

def remove_news():
    news = ROOT / "news"
    if news.exists():
        shutil.rmtree(news)
        print("OK /news/ removed")

# ── 9. FIX CHART.JS ───────────────────────────────────────────────────────────

def fix_chartjs():
    tag = '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>\n'
    keep = {ROOT / "index.html", ROOT / "bdi-chart-historical-data" / "index.html"}
    for lc in ["zh","ja","es","fr","ar","pt","ru"]:
        keep.add(ROOT / lc / "index.html")
        keep.add(ROOT / lc / "bdi-chart-historical-data" / "index.html")
    fixed = 0
    for p in ROOT.rglob("*.html"):
        if p in keep:
            continue
        c = p.read_text(encoding="utf-8")
        if tag in c:
            p.write_text(c.replace(tag, ""), encoding="utf-8")
            fixed += 1
    if fixed:
        print(f"OK Chart.js removed from {fixed} pages")

# ── MAIN ──────────────────────────────────────────────────────────────────────


def update_homepage_articles(slug, url_path, headline, date_str):
    if not INDEX_FILE.exists():
        return
    html = INDEX_FILE.read_text(encoding="utf-8")
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    date_short = dt.strftime("%b %-d, %Y")

    # Update featured article
    old_pat = r'<!-- HOMEPAGE-FEATURED-ARTICLE --><a href="[^"]*" class="article-card featured">.*?<div class="article-category">Weekly Wrap[^<]*</div>.*?<div class="article-title">[^<]*</div>'
    new_feat = (
        '<!-- HOMEPAGE-FEATURED-ARTICLE -->'
        '<a href="' + url_path + '" class="article-card featured">\n'
        '      <div class="article-category">Weekly Wrap &middot; ' + date_short + '</div>\n'
        '      <div class="article-title">' + headline + '</div>'
    )
    html = re.sub(old_pat, new_feat, html, flags=re.DOTALL)

    # Prepend sidebar item
    new_item = (
        '<a class="news-item" href="' + url_path + '">'
        '<div class="news-source">BalticDryIndex.com</div>'
        '<div class="news-headline">' + headline + '</div>'
        '<div class="news-time">' + date_short + '</div></a>'
    )
    marker = '<a class="news-item"'
    pos = html.find(marker)
    if pos > 0:
        html = html[:pos] + new_item + "\n      " + html[pos:]
        # Keep only 4 news items
        items = re.findall(r'<a class="news-item".*?</a>', html, re.DOTALL)
        if len(items) > 4:
            for old in items[4:]:
                html = html.replace("\n      " + old, "", 1)
                html = html.replace(old, "", 1)

    INDEX_FILE.write_text(html, encoding="utf-8")
    print("OK index.html sidebar + featured updated")

if __name__ == "__main__":
    data = fetch_all_data()

    if not data:
        print("No data — exiting.")
        sys.exit(1)

    # Always save the JSON data
    save_data(data)

    if DATA_ONLY:
        # ── DAILY MODE ────────────────────────────────────────────────────────
        # Only data/latest.json is updated.
        # The GitHub Actions workflow pushes this to gh-pages only.
        # Netlify never sees this commit → zero credits burned.
        print("Data-only mode complete. gh-pages will be updated by workflow.")

    else:
        # ── WEEKLY MODE ───────────────────────────────────────────────────────
        # Full update: articles, homepage pre-render, sitemap, RSS, cleanup.
        # GitHub Actions commits to main → ONE Netlify deploy per week.
        prerender_homepage(data)

        slug, url_path, headline, excerpt, article_html = generate_article(data)
        save_article(slug, article_html)
        update_analysis_index(slug, url_path, headline, excerpt, data["date"])
        update_sitemap(url_path, data["date"])
        generate_rss()
        remove_news()
        fix_chartjs()

        print(f"\nDONE: {headline}")
