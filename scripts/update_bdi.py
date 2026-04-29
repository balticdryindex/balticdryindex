#!/usr/bin/env python3
"""
BDI Daily Updater
Fetches Baltic Dry Index data from multiple free sources with fallback logic.
Generates daily blog post and updates data/latest.json
"""

import json
import os
import re
import sys
import time
import datetime
import requests
from bs4 import BeautifulSoup
from pathlib import Path

# ── CONFIG ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / 'data' / 'latest.json'
NEWS_DIR = ROOT / 'news'
SITEMAP_FILE = ROOT / 'sitemap.xml'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# ── LOAD PREVIOUS DATA ───────────────────────────────────────────────────────
def load_previous():
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except:
        return {
            "date": "2026-04-22",
            "bdi":  {"value": 2675, "prev": 2640, "change": 35,  "pct": 1.33},
            "bci":  {"value": 4356, "prev": 4300, "change": 56,  "pct": 1.30},
            "bpi":  {"value": 1971, "prev": 1973, "change": -2,  "pct": -0.10},
            "bsi":  {"value": 1484, "prev": 1443, "change": 41,  "pct": 2.84},
            "bhsi": {"value": 781,  "prev": 769,  "change": 12,  "pct": 1.56},
        }

# ── SOURCE 1: HandyBulk (most reliable free BDI source) ──────────────────────
def fetch_handybulk():
    try:
        r = requests.get('https://www.handybulk.com/baltic-dry-index/', headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'lxml')
        text = soup.get_text()
        
        # Pattern: "The Baltic Dry Index (BDI) increased/decreased by X points to reach Y points"
        bdi_match = re.search(
            r'Baltic Dry Index \(BDI\)\s+(?:increased|decreased|remained|rose|fell)[^.]*?(?:to reach|at|to)\s+([\d,]+)\s*points',
            text, re.IGNORECASE
        )
        bci_match = re.search(
            r'Baltic Capesize Index \(BCI\)\s+(?:increased|decreased|stayed|rose|fell)[^.]*?(?:to|at)\s+([\d,]+)\s*points',
            text, re.IGNORECASE
        )
        bpi_match = re.search(
            r'Baltic Panamax Index \(BPI\)\s+(?:increased|decreased|stayed|rose|fell)[^.]*?(?:to|at)\s+([\d,]+)\s*points',
            text, re.IGNORECASE
        )
        bsi_match = re.search(
            r'Baltic Supramax Index \(BSI\)\s+(?:increased|decreased|stayed|rose|fell)[^.]*?(?:to|at)\s+([\d,]+)\s*points',
            text, re.IGNORECASE
        )
        bhsi_match = re.search(
            r'Baltic Handysize Index \(BHSI\)\s+(?:increased|decreased|stayed|rose|fell)[^.]*?(?:to|at)\s+([\d,]+)\s*points',
            text, re.IGNORECASE
        )

        if not bdi_match:
            return None

        result = {}
        if bdi_match:
            result['bdi'] = int(bdi_match.group(1).replace(',', ''))
        if bci_match:
            result['bci'] = int(bci_match.group(1).replace(',', ''))
        if bpi_match:
            result['bpi'] = int(bpi_match.group(1).replace(',', ''))
        if bsi_match:
            result['bsi'] = int(bsi_match.group(1).replace(',', ''))
        if bhsi_match:
            result['bhsi'] = int(bhsi_match.group(1).replace(',', ''))

        # Also extract change values
        bdi_change_match = re.search(
            r'Baltic Dry Index \(BDI\)\s+(increased|decreased)[^.]*?by\s+([\d,]+)\s*points',
            text, re.IGNORECASE
        )
        if bdi_change_match:
            direction = bdi_change_match.group(1).lower()
            change_val = int(bdi_change_match.group(2).replace(',', ''))
            result['bdi_change'] = change_val if direction == 'increased' else -change_val

        print(f"HandyBulk: BDI={result.get('bdi')} BCI={result.get('bci')} BPI={result.get('bpi')}")
        return result if result.get('bdi') else None

    except Exception as e:
        print(f"HandyBulk failed: {e}")
        return None

# ── SOURCE 2: Hellenic Shipping News ─────────────────────────────────────────
def fetch_hellenic():
    try:
        r = requests.get(
            'https://www.hellenicshippingnews.com/category/dry-bulk-market/',
            headers=HEADERS, timeout=15
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'lxml')
        
        # Find article with BDI data
        articles = soup.find_all('article')
        for article in articles[:5]:
            text = article.get_text()
            if 'Baltic Dry Index' in text or 'BDI' in text:
                bdi_match = re.search(r'BDI[^0-9]*([\d,]{3,5})', text)
                if bdi_match:
                    val = int(bdi_match.group(1).replace(',', ''))
                    if 500 < val < 15000:  # sanity check
                        print(f"Hellenic: BDI={val}")
                        return {'bdi': val}
        return None
    except Exception as e:
        print(f"Hellenic failed: {e}")
        return None

# ── SOURCE 3: Yahoo Finance ^BDIY ────────────────────────────────────────────
def fetch_yahoo():
    try:
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/%5EBDIY?interval=1d&range=5d'
        r = requests.get(url, headers={**HEADERS, 'Accept': 'application/json'}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        result = data.get('chart', {}).get('result', [{}])[0]
        closes = result.get('indicators', {}).get('quote', [{}])[0].get('close', [])
        closes = [c for c in closes if c is not None]
        if len(closes) >= 2:
            val = round(closes[-1])
            prev = round(closes[-2])
            print(f"Yahoo: BDI={val} prev={prev}")
            return {'bdi': val, 'bdi_prev': prev}
        return None
    except Exception as e:
        print(f"Yahoo failed: {e}")
        return None

# ── SOURCE 4: Stooq ───────────────────────────────────────────────────────────
def fetch_stooq():
    try:
        url = 'https://stooq.com/q/d/l/?s=bdi.i&i=d&o=1&l=5'
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        lines = [l for l in r.text.strip().split('\n') if l and not l.startswith('Date')]
        if len(lines) >= 2:
            parts = lines[-1].split(',')
            val = round(float(parts[4] if len(parts) > 4 else parts[1]))
            prev_parts = lines[-2].split(',')
            prev = round(float(prev_parts[4] if len(prev_parts) > 4 else prev_parts[1]))
            if 500 < val < 15000:
                print(f"Stooq: BDI={val} prev={prev}")
                return {'bdi': val, 'bdi_prev': prev}
        return None
    except Exception as e:
        print(f"Stooq failed: {e}")
        return None

# ── MAIN FETCH LOGIC ──────────────────────────────────────────────────────────
def fetch_all_data():
    previous = load_previous()
    today = datetime.date.today().isoformat()

    # Skip weekends (BDI not published)
    weekday = datetime.date.today().weekday()
    if weekday >= 5:
        print(f"Weekend ({weekday}) — skipping update, keeping previous data")
        return None

    print(f"\n=== BDI Update {today} ===")

    # Try sources in order
    result = None
    for fetch_fn in [fetch_handybulk, fetch_yahoo, fetch_stooq, fetch_hellenic]:
        result = fetch_fn()
        if result and result.get('bdi'):
            break
        time.sleep(2)

    if not result or not result.get('bdi'):
        print("All sources failed — keeping previous data, updating timestamp only")
        previous['updated'] = datetime.datetime.utcnow().strftime('%H:%M UTC')
        previous['source'] = 'previous (sources unavailable)'
        return previous

    # Build new data object
    new_bdi = result.get('bdi')
    prev_bdi = result.get('bdi_prev', previous['bdi']['value'])
    bdi_change = new_bdi - prev_bdi
    bdi_pct = round((bdi_change / prev_bdi) * 100, 2) if prev_bdi else 0

    # Sub-indices: use HandyBulk values if available, else scale from previous
    ratio = new_bdi / previous['bdi']['value'] if previous['bdi']['value'] else 1

    def sub(key, handybulk_val):
        prev_val = previous[key]['value']
        new_val = handybulk_val if handybulk_val else round(prev_val * ratio)
        change = new_val - prev_val
        pct = round((change / prev_val) * 100, 2) if prev_val else 0
        return {"value": new_val, "prev": prev_val, "change": change, "pct": pct}

    data = {
        "date": today,
        "updated": datetime.datetime.utcnow().strftime('%H:%M UTC'),
        "source": "Baltic Exchange",
        "bdi":  {"value": new_bdi, "prev": prev_bdi, "change": bdi_change, "pct": bdi_pct},
        "bci":  sub('bci',  result.get('bci')),
        "bpi":  sub('bpi',  result.get('bpi')),
        "bsi":  sub('bsi',  result.get('bsi')),
        "bhsi": sub('bhsi', result.get('bhsi')),
        "routes": previous.get('routes', {}),
        "stats": previous.get('stats', {})
    }

    # Update 52w high/low
    stats = data['stats']
    if new_bdi > stats.get('week52High', 0):
        stats['week52High'] = new_bdi
    if new_bdi < stats.get('week52Low', 99999):
        stats['week52Low'] = new_bdi
    data['stats'] = stats

    print(f"\nFinal: BDI={new_bdi} ({'+' if bdi_change >= 0 else ''}{bdi_change}, {'+' if bdi_pct >= 0 else ''}{bdi_pct}%)")
    return data

# ── BLOG GENERATOR ────────────────────────────────────────────────────────────
def generate_blog_post(data):
    date_str = data['date']
    dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    date_display = dt.strftime('%B %-d, %Y')
    date_url = dt.strftime('%B-%d-%Y').lower()

    bdi = data['bdi']
    bci = data['bci']
    bpi = data['bpi']
    bsi = data['bsi']
    bhsi = data['bhsi']

    # Generate headline based on movement
    direction = 'rises' if bdi['change'] >= 0 else 'falls'
    abs_change = abs(bdi['change'])
    abs_pct = abs(bdi['pct'])

    # Find biggest mover
    movers = [
        ('Capesize', bci), ('Panamax', bpi), ('Supramax', bsi), ('Handysize', bhsi)
    ]
    biggest = max(movers, key=lambda x: abs(x[1]['pct']))

    # Headline
    if abs_pct >= 2:
        headline = f"Baltic Dry Index {direction.capitalize()} {abs_pct}% to {bdi['value']:,} — {biggest[0]} Leads Move"
    elif abs_change == 0:
        headline = f"Baltic Dry Index Holds Steady at {bdi['value']:,} on {date_display}"
    else:
        headline = f"Baltic Dry Index {direction.capitalize()} to {bdi['value']:,} on {date_display}"

    # Slug
    slug = re.sub(r'[^a-z0-9]+', '-', headline.lower()).strip('-')
    slug = f"bdi-{dt.strftime('%Y-%m-%d')}-{direction}"
    url_path = f"/news/{slug}/"

    # Article body
    arrow_bdi = '▲' if bdi['change'] >= 0 else '▼'
    sign = '+' if bdi['change'] >= 0 else ''

    # Context sentence
    if bdi['change'] > 50:
        context = "Strong buying in the dry bulk freight market pushed rates sharply higher, with tonnage demand outpacing available supply across key trade routes."
    elif bdi['change'] > 0:
        context = "Moderate improvements in freight demand supported a modest advance in the index, with shipping companies benefiting from slightly firmer cargo volumes."
    elif bdi['change'] < -50:
        context = "Easing cargo demand weighed on dry bulk rates, as reduced commodity volumes and an uptick in available tonnage put downward pressure on the index."
    elif bdi['change'] < 0:
        context = "Softer freight demand and an increase in available dry bulk vessels contributed to a modest retreat in the index."
    else:
        context = "The dry bulk freight market held steady as demand and available tonnage remained broadly balanced across major trading routes."

    # Capesize analysis
    if bci['change'] > 100:
        cape_text = f"The Capesize segment was the standout performer, rising {bci['change']:+,} points ({bci['pct']:+.2f}%) to {bci['value']:,}. Strong iron ore demand from China, particularly on the Brazil-to-Qingdao C3 route, was the primary driver. Vale's export volumes and restocking by Chinese steel mills are cited as key factors."
    elif bci['change'] > 0:
        cape_text = f"Capesize rates edged higher by {bci['change']:+,} points ({bci['pct']:+.2f}%) to {bci['value']:,}, supported by steady iron ore demand on the key Australia and Brazil routes to China."
    elif bci['change'] < -100:
        cape_text = f"Capesize rates came under significant pressure, falling {abs(bci['change']):,} points ({bci['pct']:.2f}%) to {bci['value']:,}, as iron ore cargo volumes softened and more vessels became available for fixing."
    else:
        cape_text = f"Capesize rates moved {bci['change']:+,} points ({bci['pct']:+.2f}%) to {bci['value']:,}, reflecting broadly balanced supply and demand conditions on the major iron ore corridors."

    # Panamax analysis
    if bpi['change'] > 0:
        pana_text = f"The Panamax segment gained {bpi['change']:+,} points to {bpi['value']:,}, benefiting from improved grain export volumes in the US Gulf and rising coal demand across Asian markets."
    elif bpi['change'] < 0:
        pana_text = f"Panamax rates slipped {abs(bpi['change']):,} points to {bpi['value']:,}, as grain export activity in the Atlantic remained subdued and some vessels repositioned into the Pacific basin."
    else:
        pana_text = f"Panamax rates held firm at {bpi['value']:,}, with Atlantic grain trades and Pacific coal flows providing broadly offsetting support."

    # Signal paragraph
    if bdi['value'] > 3000:
        signal = "A BDI above 3,000 is historically associated with robust global trade conditions and healthy commodity demand. Shipping companies with significant Capesize or Panamax exposure tend to benefit most from these elevated rate environments."
    elif bdi['value'] > 2000:
        signal = f"With the BDI at {bdi['value']:,}, freight rates remain in moderately positive territory. This level is consistent with solid — though not exceptional — global dry bulk trade activity, and typically supports healthy earnings for diversified dry bulk operators."
    elif bdi['value'] > 1500:
        signal = f"The BDI at {bdi['value']:,} reflects a market in recovery mode. Rates remain above the critical breakeven level for most modern vessels, but significant upside will require a sustained increase in commodity import demand, particularly from China."
    else:
        signal = f"With the BDI at {bdi['value']:,}, the freight market is under pressure. Rate levels at this range can squeeze profitability for older, less efficient vessels, and may signal a broader softening in global commodity trade flows."

    # Generate HTML article
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{headline} | BalticDryIndex.com</title>
<meta name="description" content="Baltic Dry Index {direction}s {abs_change} points to {bdi['value']:,} on {date_display}. BCI {bci['value']:,}, BPI {bpi['value']:,}, BSI {bsi['value']:,}. Daily shipping market analysis.">
<meta name="keywords" content="baltic dry index {date_display.lower()}, BDI {dt.strftime('%B %Y').lower()}, baltic dry index today, BDI news, {direction}ing BDI, capesize rates, panamax rates">
<link rel="canonical" href="https://www.balticdryindex.com{url_path}">
<meta property="og:title" content="{headline}">
<meta property="og:description" content="BDI {arrow_bdi} {sign}{bdi['change']} to {bdi['value']:,} on {date_display}. Full analysis.">
<meta property="og:type" content="article">
<meta property="og:url" content="https://www.balticdryindex.com{url_path}">
<meta name="article:published_time" content="{date_str}">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<meta name="theme-color" content="#090b0e">
<link rel="stylesheet" href="/assets/style.css">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "NewsArticle",
  "headline": "{headline}",
  "datePublished": "{date_str}",
  "dateModified": "{date_str}",
  "description": "Baltic Dry Index {direction}s to {bdi['value']:,} on {date_display}.",
  "publisher": {{"@type":"Organization","name":"BalticDryIndex.com","url":"https://www.balticdryindex.com"}},
  "mainEntityOfPage": "https://www.balticdryindex.com{url_path}"
}}
</script>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9696700979125307" crossorigin="anonymous"></script>
</head>
<body>

<div class="ticker-bar">
  <div class="ticker-label">LIVE</div>
  <div class="ticker-overflow"><div class="ticker-track" id="tickerTrack"><div class="ticker-item"><span class="t-name">BDI</span><span class="t-val">{bdi['value']:,}</span><span class="{'up' if bdi['change'] >= 0 else 'dn'}">{arrow_bdi} {sign}{bdi['change']}</span></div></div></div>
</div>

<header>
  <div class="header-inner">
    <a href="/" class="logo"><span class="logo-main">BALTIC DRY</span><span class="logo-dot">.</span><span class="logo-tag">INDEX</span></a>
    <nav>
      <a href="/">Live Data</a>
      <a href="/what-is-the-baltic-dry-index/">About BDI</a>
      <a href="/bdi-chart-historical-data/">Chart</a>
      <a href="/vessel-classes/">Vessels</a>
      <a href="/shipping-stocks/">Stocks</a>
      <a href="/news/" class="active">News</a>
      <a href="/glossary/">Glossary</a>
    </nav>
    <div class="lang-switcher"><a href="/" class="active">EN</a><a href="/zh/">中文</a><a href="/ja/">日本語</a><a href="/pt/">PT</a><a href="/ru/">RU</a></div>
  </div>
</header>

<div class="breadcrumb"><a href="/">Home</a><span>›</span><a href="/news/">News</a><span>›</span>{date_display}</div>

<div style="max-width:860px;margin:0 auto;padding:32px 24px 0;position:relative;z-index:1;">
  <div style="font-family:var(--mono);font-size:10px;letter-spacing:.2em;color:var(--gold);text-transform:uppercase;margin-bottom:10px;">BDI Daily Report · {date_display}</div>
  <h1 style="font-family:'Bebas Neue',sans-serif;font-size:clamp(28px,4vw,48px);color:#fff;letter-spacing:.02em;line-height:1.1;margin-bottom:16px;">{headline}</h1>

  <!-- BDI DATA STRIP -->
  <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:2px;margin:24px 0;">
    <div class="stat-box"><div class="stat-value {'up' if bdi['change']>=0 else 'dn'}" style="font-size:28px;">{bdi['value']:,}</div><div class="stat-label">BDI</div><div class="stat-change {'up' if bdi['change']>=0 else 'dn'}">{arrow_bdi}{sign}{bdi['change']}</div></div>
    <div class="stat-box"><div class="stat-value" style="font-size:24px;">{bci['value']:,}</div><div class="stat-label">BCI Capesize</div><div class="stat-change {'up' if bci['change']>=0 else 'dn'}">{'+' if bci['change']>=0 else ''}{bci['change']}</div></div>
    <div class="stat-box"><div class="stat-value" style="font-size:24px;">{bpi['value']:,}</div><div class="stat-label">BPI Panamax</div><div class="stat-change {'up' if bpi['change']>=0 else 'dn'}">{'+' if bpi['change']>=0 else ''}{bpi['change']}</div></div>
    <div class="stat-box"><div class="stat-value" style="font-size:24px;">{bsi['value']:,}</div><div class="stat-label">BSI Supramax</div><div class="stat-change {'up' if bsi['change']>=0 else 'dn'}">{'+' if bsi['change']>=0 else ''}{bsi['change']}</div></div>
    <div class="stat-box"><div class="stat-value" style="font-size:24px;">{bhsi['value']:,}</div><div class="stat-label">BHSI Handysize</div><div class="stat-change {'up' if bhsi['change']>=0 else 'dn'}">{'+' if bhsi['change']>=0 else ''}{bhsi['change']}</div></div>
  </div>

  <!-- AD SLOT -->
  <div style="margin:20px 0;text-align:center;">
    <ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-9696700979125307" data-ad-slot="auto" data-ad-format="auto" data-full-width-responsive="true"></ins>
    <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
  </div>

  <!-- ARTICLE -->
  <article class="prose" style="margin-top:8px;">
    <p>The <strong>Baltic Dry Index (BDI)</strong> {direction}d {abs_change} points ({sign}{bdi['pct']}%) to <strong>{bdi['value']:,}</strong> on {date_display}, according to the London-based Baltic Exchange. {context}</p>

    <h2>Capesize Rates</h2>
    <p>{cape_text}</p>

    <h2>Panamax & Smaller Vessels</h2>
    <p>{pana_text}</p>
    <p>The <strong>Supramax index</strong> moved to {bsi['value']:,} ({'+' if bsi['change']>=0 else ''}{bsi['change']} points), while the <strong>Handysize index</strong> reached {bhsi['value']:,} ({'+' if bhsi['change']>=0 else ''}{bhsi['change']} points), reflecting conditions in the minor bulk and regional trade markets.</p>

    <h2>What the BDI Signals</h2>
    <p>{signal}</p>
    <p>The BDI is published daily by the <a href="https://www.balticexchange.com" target="_blank" rel="noopener">Baltic Exchange</a> at approximately 13:00 GMT on each working day and is widely used as a leading indicator of global economic activity and commodity trade flows.</p>

    <h2>Track the BDI</h2>
    <p>Follow the Baltic Dry Index daily on <a href="/">BalticDryIndex.com</a> — including live data, sub-index tracking, <a href="/bdi-chart-historical-data/">interactive historical charts</a>, and <a href="/what-is-the-baltic-dry-index/">guides to understanding the BDI</a>.</p>

    <p style="font-family:var(--mono);font-size:10px;color:var(--text-muted);margin-top:24px;padding-top:14px;border-top:1px solid var(--border);">
      Source: Baltic Exchange via BalticDryIndex.com · Published {date_display} · Data indicative only, not financial advice. <a href="/disclaimer/">Disclaimer</a>
    </p>
  </article>

  <!-- AD SLOT -->
  <div style="margin:24px 0;text-align:center;">
    <ins class="adsbygoogle" style="display:block" data-ad-client="ca-pub-9696700979125307" data-ad-slot="auto" data-ad-format="auto" data-full-width-responsive="true"></ins>
    <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
  </div>

  <!-- BROKER STRIP -->
  <div class="broker-strip" style="margin-top:8px;">
    <div class="broker-label">Trade Shipping Stocks & Commodities — Partner Brokers</div>
    <div class="broker-grid">
      <a href="https://dukascopy.bank/swiss/open-mca-account/?ref=YJM-PUE&lang=en" class="broker-card" target="_blank" rel="noopener sponsored"><div class="broker-name">Dukascopy</div><div class="broker-desc">Swiss regulated bank and broker. Trade commodities and global markets.</div><div class="broker-cta">Open Account →</div></a>
      <a href="https://ibkr.com/referral/julio411" class="broker-card" target="_blank" rel="noopener sponsored"><div class="broker-name">IBKR</div><div class="broker-desc">Low-cost access to global markets. Trade SBLK, GOGL and dry bulk stocks.</div><div class="broker-cta">Open Account →</div></a>
      <a href="#" class="broker-card"><div class="broker-name">eToro</div><div class="broker-desc">Trade dry bulk stocks and commodities. Copy top shipping traders.</div><div class="broker-cta">Open Account →</div></a>
      <a href="#" class="broker-card"><div class="broker-name">Saxo</div><div class="broker-desc">Professional-grade access to global commodity futures and shipping equities.</div><div class="broker-cta">Open Account →</div></a>
    </div>
  </div>
</div>

<footer>
  <div class="footer-inner">
    <div><a href="/" class="logo"><span class="logo-main">BALTIC DRY</span><span class="logo-dot">.</span></a><div class="footer-tagline">The independent source for Baltic Dry Index data and shipping market intelligence.</div></div>
    <div><div class="footer-col-title">Data</div><ul class="footer-links"><li><a href="/">Live BDI Chart</a></li><li><a href="/bdi-chart-historical-data/">Historical Data</a></li><li><a href="/news/">BDI News</a></li><li><a href="/shipping-stocks/">Shipping Stocks</a></li></ul></div>
    <div><div class="footer-col-title">Company</div><ul class="footer-links"><li><a href="/about/">About</a></li><li><a href="/contact/">Contact</a></li><li><a href="/privacy-policy/">Privacy Policy</a></li><li><a href="/disclaimer/">Disclaimer</a></li></ul></div>
    <div><div class="footer-col-title">Languages</div><ul class="footer-links"><li><a href="/">English</a></li><li><a href="/zh/">中文</a></li><li><a href="/ja/">日本語</a></li><li><a href="/pt/">Português</a></li><li><a href="/ru/">Русский</a></li></ul></div>
  </div>
  <div class="footer-bottom"><div class="footer-copy">© 2026 Sea Blast LTD · BalticDryIndex.com</div><div class="footer-disclaimer">Data indicative only. Not financial advice. <a href="/disclaimer/" style="color:var(--text-muted);">Disclaimer</a></div></div>
</footer>

<script src="/assets/bdi.js"></script>
<script>
BDI.load(function(d){ BDI.buildTicker(d); });
</script>
</body>
</html>'''

    return slug, url_path, headline, html

# ── SAVE DATA ─────────────────────────────────────────────────────────────────
def save_data(data):
    DATA_FILE.parent.mkdir(exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Saved: {DATA_FILE}")

# ── SAVE BLOG POST ────────────────────────────────────────────────────────────
def save_blog_post(slug, html):
    post_dir = NEWS_DIR / slug
    post_dir.mkdir(parents=True, exist_ok=True)
    post_file = post_dir / 'index.html'
    with open(post_file, 'w') as f:
        f.write(html)
    print(f"Blog post saved: {post_file}")
    return str(post_dir)

# ── UPDATE NEWS INDEX ─────────────────────────────────────────────────────────
def update_news_index():
    """Generate /news/index.html from all existing posts"""
    posts = []
    if NEWS_DIR.exists():
        for post_dir in sorted(NEWS_DIR.iterdir(), reverse=True):
            if post_dir.is_dir() and (post_dir / 'index.html').exists():
                # Extract title from HTML
                with open(post_dir / 'index.html') as f:
                    content = f.read()
                title_match = re.search(r'<title>(.*?)\s*\|', content)
                date_match = re.search(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})"', content)
                if title_match and date_match:
                    posts.append({
                        'slug': post_dir.name,
                        'title': title_match.group(1),
                        'date': date_match.group(1)
                    })

    articles_html = ''
    for p in posts[:50]:
        dt = datetime.datetime.strptime(p['date'], '%Y-%m-%d')
        articles_html += f'''
    <a href="/news/{p['slug']}/" style="background:var(--surface);border:1px solid var(--border);padding:20px;text-decoration:none;display:block;margin-bottom:2px;transition:border-color .2s;" onmouseover="this.style.borderColor='var(--border2)'" onmouseout="this.style.borderColor='var(--border)'">
      <div style="font-family:var(--mono);font-size:9px;letter-spacing:.15em;color:var(--gold-dim);text-transform:uppercase;margin-bottom:6px;">{dt.strftime('%B %-d, %Y')}</div>
      <div style="font-size:15px;font-weight:500;color:var(--text);line-height:1.35;">{p['title']}</div>
    </a>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Baltic Dry Index News & Daily Analysis | BalticDryIndex.com</title>
<meta name="description" content="Daily Baltic Dry Index news, BDI analysis, and shipping market reports. Updated every trading day.">
<meta name="keywords" content="baltic dry index news, BDI news today, baltic dry index analysis, BDI daily report, shipping market news">
<link rel="canonical" href="https://www.balticdryindex.com/news/">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<meta name="theme-color" content="#090b0e">
<link rel="stylesheet" href="/assets/style.css">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-9696700979125307" crossorigin="anonymous"></script>
</head>
<body>
<div class="ticker-bar"><div class="ticker-label">LIVE</div><div class="ticker-overflow"><div class="ticker-track" id="tickerTrack"><div class="ticker-item"><span class="t-name">BDI</span><span class="t-val"><span class="spin"></span></span></div></div></div></div>
<header>
  <div class="header-inner">
    <a href="/" class="logo"><span class="logo-main">BALTIC DRY</span><span class="logo-dot">.</span><span class="logo-tag">INDEX</span></a>
    <nav><a href="/">Live Data</a><a href="/what-is-the-baltic-dry-index/">About BDI</a><a href="/bdi-chart-historical-data/">Chart</a><a href="/vessel-classes/">Vessels</a><a href="/shipping-stocks/">Stocks</a><a href="/news/" class="active">News</a><a href="/glossary/">Glossary</a></nav>
  </div>
</header>
<div class="breadcrumb"><a href="/">Home</a><span>›</span>News & Analysis</div>
<div class="page-hero">
  <div class="page-eyebrow"><span class="live-dot"></span>Updated Daily</div>
  <h1 class="page-title">BDI <span>News & Analysis</span></h1>
  <p class="page-desc">Daily Baltic Dry Index reports, shipping market analysis, and freight rate commentary — published every trading day.</p>
</div>
<div style="max-width:860px;margin:0 auto;padding:0 24px 60px;position:relative;z-index:1;">
{articles_html if articles_html else '<p style="color:var(--text-dim);padding:20px 0;">Daily reports will appear here. Check back tomorrow.</p>'}
</div>
<footer>
  <div class="footer-inner">
    <div><a href="/" class="logo"><span class="logo-main">BALTIC DRY</span><span class="logo-dot">.</span></a><div class="footer-tagline">The independent source for Baltic Dry Index data and shipping market intelligence.</div></div>
    <div><div class="footer-col-title">Data</div><ul class="footer-links"><li><a href="/">Live BDI Chart</a></li><li><a href="/bdi-chart-historical-data/">Historical Data</a></li><li><a href="/news/">BDI News</a></li></ul></div>
    <div><div class="footer-col-title">Company</div><ul class="footer-links"><li><a href="/about/">About</a></li><li><a href="/contact/">Contact</a></li><li><a href="/privacy-policy/">Privacy Policy</a></li><li><a href="/disclaimer/">Disclaimer</a></li></ul></div>
    <div><div class="footer-col-title">Languages</div><ul class="footer-links"><li><a href="/">English</a></li><li><a href="/zh/">中文</a></li><li><a href="/ja/">日本語</a></li><li><a href="/pt/">Português</a></li><li><a href="/ru/">Русский</a></li></ul></div>
  </div>
  <div class="footer-bottom"><div class="footer-copy">© 2026 Sea Blast LTD · BalticDryIndex.com</div><div class="footer-disclaimer">Not financial advice.</div></div>
</footer>
<script src="/assets/bdi.js"></script>
<script>BDI.load(function(d){{BDI.buildTicker(d);}});</script>
</body>
</html>'''

    news_index = NEWS_DIR / 'index.html'
    with open(news_index, 'w') as f:
        f.write(html)
    print(f"News index updated: {news_index}")

# ── UPDATE SITEMAP ─────────────────────────────────────────────────────────────
def update_sitemap(new_posts):
    """Append new post URLs to sitemap"""
    try:
        with open(SITEMAP_FILE) as f:
            sitemap = f.read()
    except:
        sitemap = ''

    today = datetime.date.today().isoformat()
    for slug, url_path in new_posts:
        if url_path not in sitemap:
            new_url = f'''  <url><loc>https://www.balticdryindex.com{url_path}</loc><changefreq>monthly</changefreq><priority>0.7</priority><lastmod>{today}</lastmod></url>'''
            sitemap = sitemap.replace('</urlset>', new_url + '\n</urlset>')

    with open(SITEMAP_FILE, 'w') as f:
        f.write(sitemap)
    print("Sitemap updated")

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    NEWS_DIR.mkdir(exist_ok=True)

    data_only = '--data-only' in sys.argv
    news_only = '--news-only' in sys.argv

    data = fetch_all_data()

    if data is None:
        print("Weekend or no update needed")
        if not data_only:
            update_news_index()
        sys.exit(0)

    save_data(data)

    if data_only:
        print("\n✓ Data-only update complete")
        sys.exit(0)

    slug, url_path, headline, html = generate_blog_post(data)
    save_blog_post(slug, html)

    update_news_index()
    update_sitemap([(slug, url_path)])

    print(f"\n✓ Complete: {headline}")