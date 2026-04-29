#!/usr/bin/env python3
"""
Production Baltic Dry Index updater.

Modes:
  python scripts/update_bdi.py --data-only   -> updates data/latest.json only
  python scripts/update_bdi.py               -> updates data + weekly/news files

Data sources:
  1. HandyBulk public BDI page
  2. Yahoo Finance ^BDIY
  3. Stooq BDI daily CSV
  4. Hellenic Shipping News fallback
"""

import datetime
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "latest.json"
NEWS_DIR = ROOT / "news"
SITEMAP_FILE = ROOT / "sitemap.xml"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def load_previous():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "date": "2026-04-23",
            "updated": "13:00 UTC",
            "source": "fallback",
            "bdi": {"value": 2675, "prev": 2640, "change": 35, "pct": 1.33},
            "bci": {"value": 4356, "prev": 4300, "change": 56, "pct": 1.30},
            "bpi": {"value": 1971, "prev": 1973, "change": -2, "pct": -0.10},
            "bsi": {"value": 1484, "prev": 1443, "change": 41, "pct": 2.84},
            "bhsi": {"value": 781, "prev": 769, "change": 12, "pct": 1.56},
            "stats": {"week52High": 2845, "week52Low": 1261},
        }


def clean_int(value):
    return int(str(value).replace(",", "").strip())


def valid_bdi(value):
    return isinstance(value, int) and 300 <= value <= 15000


def fetch_handybulk():
    try:
        url = "https://www.handybulk.com/baltic-dry-index/"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "lxml")
        text = " ".join(soup.get_text(" ").split())

        result = {"source": "HandyBulk"}

        patterns = {
            "bdi": r"BDI\)?[^.]{0,160}?(?:to|at|reached|reach)\s+([\d,]{3,6})\s*(?:points|point)?",
            "bci": r"BCI\)?[^.]{0,160}?(?:to|at|reached|reach)\s+([\d,]{3,6})\s*(?:points|point)?",
            "bpi": r"BPI\)?[^.]{0,160}?(?:to|at|reached|reach)\s+([\d,]{3,6})\s*(?:points|point)?",
            "bsi": r"BSI\)?[^.]{0,160}?(?:to|at|reached|reach)\s+([\d,]{3,6})\s*(?:points|point)?",
            "bhsi": r"BHSI\)?[^.]{0,160}?(?:to|at|reached|reach)\s+([\d,]{3,6})\s*(?:points|point)?",
        }

        full_patterns = {
            "bdi": r"Baltic Dry Index[^.]{0,180}?(?:to|at|reached|reach)\s+([\d,]{3,6})\s*(?:points|point)?",
            "bci": r"Baltic Capesize Index[^.]{0,180}?(?:to|at|reached|reach)\s+([\d,]{3,6})\s*(?:points|point)?",
            "bpi": r"Baltic Panamax Index[^.]{0,180}?(?:to|at|reached|reach)\s+([\d,]{3,6})\s*(?:points|point)?",
            "bsi": r"Baltic Supramax Index[^.]{0,180}?(?:to|at|reached|reach)\s+([\d,]{3,6})\s*(?:points|point)?",
            "bhsi": r"Baltic Handysize Index[^.]{0,180}?(?:to|at|reached|reach)\s+([\d,]{3,6})\s*(?:points|point)?",
        }

        for key in ["bdi", "bci", "bpi", "bsi", "bhsi"]:
            match = re.search(full_patterns[key], text, re.IGNORECASE)
            if not match:
                match = re.search(patterns[key], text, re.IGNORECASE)
            if match:
                val = clean_int(match.group(1))
                if key != "bdi" or valid_bdi(val):
                    result[key] = val

        change_match = re.search(
            r"(?:BDI|Baltic Dry Index)[^.]{0,120}?(increased|rose|gained|decreased|fell|lost|declined)[^.]{0,80}?by\s+([\d,]+)",
            text,
            re.IGNORECASE,
        )
        if change_match:
            direction = change_match.group(1).lower()
            ch = clean_int(change_match.group(2))
            if direction in ["decreased", "fell", "lost", "declined"]:
                ch = -ch
            result["bdi_change"] = ch

        if result.get("bdi"):
            print(f"HandyBulk: BDI={result.get('bdi')}")
            return result

        return None

    except Exception as e:
        print(f"HandyBulk failed: {e}")
        return None


def fetch_yahoo():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EBDIY?interval=1d&range=10d"
        r = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=20)
        if r.status_code != 200:
            return None

        data = r.json()
        result = data.get("chart", {}).get("result", [{}])[0]
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        closes = [round(c) for c in closes if c is not None]

        if len(closes) >= 2 and valid_bdi(closes[-1]):
            print(f"Yahoo: BDI={closes[-1]} prev={closes[-2]}")
            return {
                "source": "Yahoo Finance",
                "bdi": closes[-1],
                "bdi_prev": closes[-2],
            }

        return None

    except Exception as e:
        print(f"Yahoo failed: {e}")
        return None


def fetch_stooq():
    try:
        url = "https://stooq.com/q/d/l/?s=bdi.i&i=d&o=1&l=10"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None

        lines = [line.strip() for line in r.text.splitlines() if line.strip() and not line.startswith("Date")]

        if len(lines) >= 2:
            latest = lines[-1].split(",")
            prev = lines[-2].split(",")

            latest_val = round(float(latest[4] if len(latest) > 4 else latest[1]))
            prev_val = round(float(prev[4] if len(prev) > 4 else prev[1]))

            if valid_bdi(latest_val):
                print(f"Stooq: BDI={latest_val} prev={prev_val}")
                return {
                    "source": "Stooq",
                    "bdi": latest_val,
                    "bdi_prev": prev_val,
                }

        return None

    except Exception as e:
        print(f"Stooq failed: {e}")
        return None


def fetch_hellenic():
    try:
        url = "https://www.hellenicshippingnews.com/category/dry-bulk-market/"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "lxml")
        text = " ".join(soup.get_text(" ").split())

        match = re.search(r"(?:Baltic Dry Index|BDI)[^0-9]{0,80}([\d,]{3,6})", text, re.IGNORECASE)
        if match:
            val = clean_int(match.group(1))
            if valid_bdi(val):
                print(f"Hellenic: BDI={val}")
                return {"source": "Hellenic Shipping News", "bdi": val}

        return None

    except Exception as e:
        print(f"Hellenic failed: {e}")
        return None


def build_index(current_value, previous_value):
    change = current_value - previous_value
    pct = round((change / previous_value) * 100, 2) if previous_value else 0
    return {
        "value": current_value,
        "prev": previous_value,
        "change": change,
        "pct": pct,
    }


def fetch_all_data():
    previous = load_previous()
    today = datetime.date.today()

    if today.weekday() >= 5:
        print("Weekend — no BDI publication expected.")
        return None

    print(f"=== BDI Update {today.isoformat()} ===")

    result = None
    for source in [fetch_handybulk, fetch_yahoo, fetch_stooq, fetch_hellenic]:
        result = source()
        if result and result.get("bdi"):
            break
        time.sleep(2)

    if not result or not result.get("bdi"):
        print("All sources failed — keeping previous values but updating timestamp.")
        previous["updated"] = datetime.datetime.utcnow().strftime("%H:%M UTC")
        previous["source"] = "previous values - sources unavailable"
        return previous

    new_bdi = int(result["bdi"])

    if result.get("bdi_prev"):
        prev_bdi = int(result["bdi_prev"])
    elif result.get("bdi_change") is not None:
        prev_bdi = new_bdi - int(result["bdi_change"])
    else:
        prev_bdi = int(previous["bdi"]["value"])

    data = {
        "date": today.isoformat(),
        "updated": datetime.datetime.utcnow().strftime("%H:%M UTC"),
        "source": result.get("source", "public market source"),
        "bdi": build_index(new_bdi, prev_bdi),
        "bci": build_index(int(result.get("bci", previous["bci"]["value"])), int(previous["bci"]["value"])),
        "bpi": build_index(int(result.get("bpi", previous["bpi"]["value"])), int(previous["bpi"]["value"])),
        "bsi": build_index(int(result.get("bsi", previous["bsi"]["value"])), int(previous["bsi"]["value"])),
        "bhsi": build_index(int(result.get("bhsi", previous["bhsi"]["value"])), int(previous["bhsi"]["value"])),
        "stats": previous.get("stats", {}),
    }

    stats = data["stats"]
    stats["week52High"] = max(stats.get("week52High", new_bdi), new_bdi)
    stats["week52Low"] = min(stats.get("week52Low", new_bdi), new_bdi)
    data["stats"] = stats

    print(f"Final BDI: {data['bdi']['value']} ({data['bdi']['change']:+}) from {data['source']}")
    return data


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {DATA_FILE}")


def generate_blog_post(data):
    dt = datetime.datetime.strptime(data["date"], "%Y-%m-%d")
    date_display = dt.strftime("%B %-d, %Y")
    bdi = data["bdi"]

    movement = "rises" if bdi["change"] >= 0 else "falls"
    headline = f"Baltic Dry Index {movement} to {bdi['value']:,} on {date_display}"
    slug = f"bdi-{dt.strftime('%Y-%m-%d')}-{movement}"
    url_path = f"/news/{slug}/"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{headline} | BalticDryIndex.com</title>
<meta name="description" content="Baltic Dry Index update for {date_display}. BDI closed at {bdi['value']:,}, changing {bdi['change']:+} points.">
<link rel="canonical" href="https://www.balticdryindex.com{url_path}">
<link rel="stylesheet" href="/assets/style.css">
</head>
<body>
<header>
  <div class="header-inner">
    <a href="/" class="logo"><span class="logo-main">BALTIC DRY</span><span class="logo-dot">.</span><span class="logo-tag">INDEX</span></a>
  </div>
</header>

<main style="max-width:860px;margin:40px auto;padding:24px;">
  <p style="font-family:var(--mono);font-size:11px;color:var(--gold);text-transform:uppercase;">BDI Weekly Market Update · {date_display}</p>
  <h1>{headline}</h1>

  <p>The Baltic Dry Index (BDI) closed at <strong>{bdi['value']:,}</strong> on {date_display}, changing <strong>{bdi['change']:+}</strong> points from the previous reading.</p>

  <p>The Capesize index stood at <strong>{data['bci']['value']:,}</strong>, Panamax at <strong>{data['bpi']['value']:,}</strong>, Supramax at <strong>{data['bsi']['value']:,}</strong>, and Handysize at <strong>{data['bhsi']['value']:,}</strong>.</p>

  <p>The BDI is widely followed as a signal of dry bulk shipping demand and global commodity trade conditions.</p>

  <p><a href="/">Track today’s Baltic Dry Index</a> or view the <a href="/bdi-chart-historical-data/">BDI historical chart</a>.</p>
</main>

<script src="/assets/bdi.js"></script>
<script>
BDI.load(function(d){{ BDI.buildTicker(d); }});
</script>
</body>
</html>
"""
    return slug, url_path, headline, html


def save_blog_post(slug, html):
    post_dir = NEWS_DIR / slug
    post_dir.mkdir(parents=True, exist_ok=True)
    with open(post_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved blog post {post_dir}")


def update_news_index():
    NEWS_DIR.mkdir(parents=True, exist_ok=True)

    posts = []
    for post_dir in sorted(NEWS_DIR.iterdir(), reverse=True):
        if post_dir.is_dir() and (post_dir / "index.html").exists():
            with open(post_dir / "index.html", "r", encoding="utf-8") as f:
                content = f.read()
            title_match = re.search(r"<title>(.*?)\s*\|", content)
            if title_match:
                posts.append((post_dir.name, title_match.group(1)))

    items = "\n".join(
        f'<li><a href="/news/{slug}/">{title}</a></li>'
        for slug, title in posts[:50]
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Baltic Dry Index News | BalticDryIndex.com</title>
<meta name="description" content="Baltic Dry Index news, weekly reports, and dry bulk market updates.">
<link rel="stylesheet" href="/assets/style.css">
</head>
<body>
<main style="max-width:860px;margin:40px auto;padding:24px;">
<h1>Baltic Dry Index News</h1>
<ul>
{items if items else "<li>No reports published yet.</li>"}
</ul>
</main>
<script src="/assets/bdi.js"></script>
<script>
BDI.load(function(d){{ BDI.buildTicker(d); }});
</script>
</body>
</html>
"""
    with open(NEWS_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Updated news index")


def update_sitemap(posts):
    today = datetime.date.today().isoformat()

    if not SITEMAP_FILE.exists():
        sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n</urlset>'
    else:
        with open(SITEMAP_FILE, "r", encoding="utf-8") as f:
            sitemap = f.read()

    for _, url_path in posts:
        if url_path not in sitemap:
            entry = f'  <url><loc>https://www.balticdryindex.com{url_path}</loc><lastmod>{today}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>\n'
            sitemap = sitemap.replace("</urlset>", entry + "</urlset>")

    with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
        f.write(sitemap)

    print("Updated sitemap")


if __name__ == "__main__":
    NEWS_DIR.mkdir(parents=True, exist_ok=True)

    data_only = "--data-only" in sys.argv

    data = fetch_all_data()

    if data is None:
        print("No update produced.")
        sys.exit(0)

    save_data(data)

    if data_only:
        print("Data-only update complete.")
        sys.exit(0)

    slug, url_path, headline, html = generate_blog_post(data)
    save_blog_post(slug, html)
    update_news_index()
    update_sitemap([(slug, url_path)])

    print(f"Complete: {headline}")
