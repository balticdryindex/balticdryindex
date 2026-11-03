#!/usr/bin/env python3
"""
BalticDryIndex.com — Daily News Autoposter

Runs every weekday after the data fetch (daily-data.yml). Writes Markdown files
to content/news/. The existing build-news.yml workflow then renders those into
styled HTML under /news/ and commits to main → Cloudflare deploys.

THREE ARTICLE TYPES produced each run:

  1. BDI MARKET BRIEF  (every run, Mon–Fri)
     Grounded in today's data/latest.json and data/history.json.
     Skipped if an article for today already exists.

  2. BALTIC SEA WEATHER  (every run, Mon–Fri)
     Fetches live marine conditions from SMHI Open Data API (CC BY 4.0).
     Covers 4 Baltic Sea sub-regions: Stockholm Archipelago, Gulf of Finland,
     Bornholm Basin, Gulf of Riga.
     Skipped if a weather article for today already exists.

  3. SHIPPING POLICY NEWS  (when new items available, ≤2 per run)
     Pulls EMSA (European Maritime Safety Agency) press releases RSS.
     EU agency content — reuse with attribution is standard EU open policy.
     Rewrites each item in original prose via OpenRouter LLM.
     Skipped entirely if OPENROUTER_API_KEY is not set.

LLM (OpenRouter) is used for:
  - BDI market brief prose (falls back to template if no key)
  - Weather article prose (falls back to template if no key)
  - EMSA article rewrites (skipped entirely if no key)

SEEN-FILE: content/news/.autopost_seen.json — tracks slugs already written so
  the script never duplicates an article across runs.

Run from the repo root:
  python scripts/autopost_news.py

Environment variables:
  OPENROUTER_API_KEY   — required to unlock LLM prose (optional, falls back gracefully)
  OPENROUTER_MODEL     — optional; default is a free/cheap model
"""

import datetime
import json
import os
import re
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

ROOT        = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "news"
DATA_FILE   = ROOT / "data" / "latest.json"
HISTORY_FILE= ROOT / "data" / "history.json"
SEEN_FILE   = CONTENT_DIR / ".autopost_seen.json"
SITE_URL    = "https://www.balticdryindex.com"

OPENROUTER_KEY      = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL    = os.environ.get("OPENROUTER_MODEL", "google/gemini-flash-1.5")
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Baltic Sea sub-regions for weather: (label, lat, lon)
WEATHER_REGIONS = [
    ("Stockholm Archipelago",  59.3,  18.9),
    ("Gulf of Finland",        60.0,  25.0),
    ("Bornholm Basin",         55.2,  15.5),
    ("Gulf of Riga",           57.5,  23.5),
]

EMSA_RSS = "https://www.emsa.europa.eu/newsroom/press-releases.feed?type=rss&format=feed"

# ── HELPERS ───────────────────────────────────────────────────────────────────

def today_iso():
    return datetime.date.today().isoformat()

def slugify(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80]

def load_seen():
    try:
        return set(json.loads(SEEN_FILE.read_text()))
    except Exception:
        return set()

def save_seen(seen):
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=2))

def write_post(slug, title, date, description, author, body):
    """Write a Markdown post to content/news/<slug>.md"""
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    path = CONTENT_DIR / f"{slug}.md"
    # Escape any YAML-breaking characters in title/description
    safe_title = title.replace('"', "'")
    safe_desc  = description.replace('"', "'")
    content = f"""---
title: "{safe_title}"
date: {date}
description: "{safe_desc}"
author: {author}
---

{body}
"""
    path.write_text(content, encoding="utf-8")
    print(f"  wrote content/news/{slug}.md")
    return slug

def llm_call(prompt, max_tokens=900):
    """Call OpenRouter. Returns text or None on any failure."""
    if not OPENROUTER_KEY:
        return None
    body = json.dumps({
        "model": OPENROUTER_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_ENDPOINT, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "HTTP-Referer": SITE_URL,
            "X-Title": "BalticDryIndex News Autoposter",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        # Strip any accidental markdown fences
        text = re.sub(r"^```(?:markdown|md|html)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
        return text if text else None
    except Exception as e:
        print(f"  llm_call failed: {e}")
        return None

def fetch_url(url, timeout=20):
    """Return response text or None."""
    req = urllib.request.Request(url, headers={"User-Agent": "BalticDryIndex-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  fetch failed {url}: {e}")
        return None

# ── 1. BDI MARKET BRIEF ───────────────────────────────────────────────────────

def load_data():
    try:
        return json.loads(DATA_FILE.read_text())
    except Exception as e:
        print(f"  cannot read data/latest.json: {e}")
        return None

def load_history():
    try:
        raw = json.loads(HISTORY_FILE.read_text())
        return raw if isinstance(raw, list) else raw.get("series", [])
    except Exception:
        return []

def _trend_word(vals, window):
    if len(vals) < 3:
        return "mixed"
    recent = vals[-window:]
    if recent[-1] > recent[0] * 1.01:
        return "rising"
    if recent[-1] < recent[0] * 0.99:
        return "falling"
    return "steady"

def _pct_str(pct):
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"

def _val(idx):
    return f"{idx['value']:,}"

def _chg(idx):
    sign = "+" if idx["change"] >= 0 else ""
    return f"{sign}{idx['change']}"

def build_bdi_brief(data, history):
    """Generate a BDI market brief article. Returns (title, description, body)."""
    date   = data["date"]
    bdi    = data["bdi"]
    bci    = data["bci"]
    bpi    = data["bpi"]
    bsi    = data["bsi"]
    bhsi   = data["bhsi"]
    stats  = data.get("stats", {})

    vals = [r["bdi"] for r in history] if history else []
    trend_5d  = _trend_word(vals, 5)
    trend_20d = _trend_word(vals, 20)

    # Build facts block for LLM and for template fallback
    facts = (
        f"Date: {date}\n"
        f"BDI: {_val(bdi)} ({_chg(bdi)}, {_pct_str(bdi['pct'])})\n"
        f"BCI Capesize: {_val(bci)} ({_chg(bci)}, {_pct_str(bci['pct'])})\n"
        f"BPI Panamax: {_val(bpi)} ({_chg(bpi)}, {_pct_str(bpi['pct'])})\n"
        f"BSI Supramax: {_val(bsi)} ({_chg(bsi)}, {_pct_str(bsi['pct'])})\n"
        f"BHSI Handysize: {_val(bhsi)} ({_chg(bhsi)}, {_pct_str(bhsi['pct'])})\n"
        f"52-week high: {stats.get('week52High', 'n/a')}  52-week low: {stats.get('week52Low', 'n/a')}\n"
        f"YTD change: {stats.get('ytdPct', 'n/a')}%  Capesize TCE: ${stats.get('capesizeTCE', 'n/a'):,}/day\n"
        f"5-day trend: {trend_5d}  20-day trend: {trend_20d}\n"
        f"History rows available: {len(vals)}"
    )

    # Headline
    direction = "rises" if bdi["change"] > 0 else "falls" if bdi["change"] < 0 else "holds steady"
    dt = datetime.date.fromisoformat(date)
    weekday = dt.strftime("%A")
    title = f"Baltic Dry Index {direction} to {_val(bdi)} on {weekday}"
    description = (
        f"The Baltic Dry Index {direction} {abs(bdi['change'])} points to {_val(bdi)} "
        f"({_pct_str(bdi['pct'])}) on {date}. Capesize at {_val(bci)}, "
        f"Panamax at {_val(bpi)}, Supramax at {_val(bsi)}."
    )

    # LLM prose (falls back to template)
    prompt = (
        "You are a dry bulk shipping market writer for BalticDryIndex.com. "
        "Write a concise daily BDI market brief using ONLY the figures below. "
        "Do not invent specific vessel names, company names, port names, or quotes. "
        "You may mention in general terms: iron ore, coal, grain, soya, bauxite flows; "
        "Brazil–China, West Australia–China, US Gulf, Black Sea, Pacific Basin routes; "
        "tonnage supply, ballasting, port congestion, seasonal demand patterns.\n\n"
        f"FIGURES:\n{facts}\n\n"
        "Write 4 paragraphs (~250–320 words total). "
        "Para 1: lead with the BDI move and what it signals. "
        "Para 2: Capesize — what is driving rates. "
        "Para 3: Panamax, Supramax and Handysize together. "
        "Para 4: forward look — what the current level implies for the near term. "
        "Tone: neutral, professional, fact-based. "
        "Return plain Markdown paragraphs only — no headings, no bullet lists, no preamble."
    )

    llm_prose = llm_call(prompt)

    if llm_prose:
        body = llm_prose
    else:
        # Template fallback — always works even with no LLM key
        up_dn = "edged higher" if bdi["change"] > 0 else "slipped" if bdi["change"] < 0 else "held steady"
        body = (
            f"The **Baltic Dry Index** {up_dn} {abs(bdi['change'])} points to "
            f"**{_val(bdi)}** on {date} ({_pct_str(bdi['pct'])}), as dry bulk freight markets "
            f"continued to reflect {trend_5d} momentum across vessel classes.\n\n"
            f"**Capesize** earnings tracked {_val(bci)} ($ {_chg(bci)}/day basis TCE), "
            f"taking direction from iron ore and coal flows on the major deep-sea routes. "
            f"The segment remains the primary driver of headline index moves given its weighting.\n\n"
            f"**Panamax** rates settled at {_val(bpi)} ({_chg(bpi)}), with grain and coal "
            f"shipments providing the main support. **Supramax** at {_val(bsi)} "
            f"({_chg(bsi)}) and **Handysize** at {_val(bhsi)} ({_chg(bhsi)}) "
            f"reflected balanced supply and demand across the smaller bulker segments.\n\n"
            f"With the 52-week range running from {stats.get('week52Low', 'n/a')} to "
            f"{stats.get('week52High', 'n/a')}, the current reading places the index in the "
            f"{'upper half' if bdi['value'] > (stats.get('week52Low',0) + stats.get('week52High',9999))//2 else 'lower half'} "
            f"of its recent range, suggesting {'constructive' if trend_20d == 'rising' else 'cautious'} "
            f"conditions for vessel owners.\n\n"
            f"For live data across all five indices, see the [BDI homepage](/), "
            f"the [historical chart](/bdi-chart-historical-data/), or run a voyage with the "
            f"[TCE calculator](/tce-calculator/).\n\n"
            f"*Data indicative. Not financial advice. [Disclaimer](/disclaimer/)*"
        )

    # Add source footer if LLM wrote the body
    if llm_prose:
        body += (
            "\n\n---\n\n"
            "For live data across all five indices, see the [BDI homepage](/), "
            "the [historical chart](/bdi-chart-historical-data/), or run a voyage with the "
            "[TCE calculator](/tce-calculator/).\n\n"
            "*Data indicative. Not financial advice. [Disclaimer](/disclaimer/)*"
        )

    return title, description, body


def run_bdi_brief(seen):
    date = today_iso()
    slug = f"bdi-{date}"
    if slug in seen:
        print(f"[BDI brief] already posted today ({slug}), skipping.")
        return seen

    data = load_data()
    if not data:
        print("[BDI brief] no data available, skipping.")
        return seen

    if data.get("date") != date:
        print(f"[BDI brief] data/latest.json is from {data.get('date')}, not today — skipping.")
        return seen

    history = load_history()
    print(f"[BDI brief] writing {slug} …")
    title, description, body = build_bdi_brief(data, history)
    write_post(slug, title, date, description, "BalticDryIndex.com", body)
    seen.add(slug)
    return seen


# ── 2. BALTIC SEA WEATHER ─────────────────────────────────────────────────────

def fetch_smhi_marine(lat, lon):
    """
    Fetch marine forecast from SMHI Open Data API (CC BY 4.0).
    Returns dict with wind_speed, wind_dir, wave_height, visibility or None.
    SMHI pointforecast for the Baltic Sea.
    """
    # SMHI Open Data API — meteorological forecasts (PMPFREKV2)
    url = (
        f"https://opendata-download-metfcst.smhi.se/api/category/pmp3g/version/2"
        f"/geotype/point/lon/{lon}/lat/{lat}/data.json"
    )
    raw = fetch_url(url, timeout=15)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        series = payload.get("timeSeries", [])
        if not series:
            return None
        # Take the first (most current) time step
        entry = series[0]
        params = {p["name"]: p["values"][0] for p in entry.get("parameters", []) if p.get("values")}
        return {
            "wind_speed":  params.get("ws"),    # m/s
            "wind_dir":    params.get("wd"),    # degrees
            "wind_gust":   params.get("gust"),  # m/s
            "visibility":  params.get("vis"),   # km
            "temp":        params.get("t"),     # °C
            "precip":      params.get("pcat"),  # precipitation category 0-6
            "valid_time":  entry.get("validTime", ""),
        }
    except Exception as e:
        print(f"  SMHI parse error: {e}")
        return None


def _wind_dir_label(deg):
    if deg is None:
        return "variable"
    dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    return dirs[round(deg / 22.5) % 16]

def _beaufort(ms):
    if ms is None:
        return "?"
    thresholds = [0.3,1.5,3.3,5.5,7.9,10.7,13.8,17.1,20.7,24.4,28.4,32.6]
    for i, t in enumerate(thresholds):
        if ms < t:
            return str(i)
    return "12"

def _sea_state(ms):
    if ms is None:
        return "unknown"
    if ms < 3.3:  return "calm to light breeze — smooth seas"
    if ms < 5.5:  return "gentle to moderate breeze — slight seas"
    if ms < 7.9:  return "fresh breeze — moderate seas"
    if ms < 10.7: return "strong breeze — rough seas"
    if ms < 13.8: return "near gale — very rough seas"
    return "gale or above — high seas"

def build_weather_article(regions_data, date):
    """Build weather article from SMHI data. Returns (title, description, body)."""
    dt      = datetime.date.fromisoformat(date)
    weekday = dt.strftime("%A, %-d %B %Y")
    title   = f"Baltic Sea Weather Briefing — {dt.strftime('%-d %B %Y')}"
    description = (
        f"Baltic Sea marine weather briefing for {dt.strftime('%-d %B %Y')}: "
        f"wind, sea state and visibility across the Stockholm Archipelago, "
        f"Gulf of Finland, Bornholm Basin and Gulf of Riga."
    )

    # Build a data summary for the LLM
    region_lines = []
    for name, obs in regions_data:
        if obs:
            ws   = obs.get("wind_speed")
            wd   = obs.get("wind_dir")
            gust = obs.get("wind_gust")
            temp = obs.get("temp")
            line = (
                f"- {name}: wind {ws} m/s ({_beaufort(ws)} Bft) from "
                f"{_wind_dir_label(wd)}, gust {gust} m/s, "
                f"{_sea_state(ws)}, temp {temp}°C"
            )
        else:
            line = f"- {name}: data unavailable"
        region_lines.append(line)
    data_block = "\n".join(region_lines)

    prompt = (
        "You are a maritime weather briefing writer for BalticDryIndex.com. "
        "Write a concise Baltic Sea weather article for dry bulk shipping operators "
        "using ONLY the figures below. Focus on practical implications: "
        "vessel operations, port approaches, sea state for bulk carriers. "
        "Do not invent figures not given.\n\n"
        f"Date: {weekday}\n"
        f"Regions:\n{data_block}\n\n"
        "Write 3–4 short paragraphs (~200–260 words). "
        "Open with an overview of conditions across the Baltic. "
        "Cover each region briefly. "
        "Close with a sentence on operational implications for vessels in the region. "
        "Tone: professional, practical, concise. "
        "Return plain Markdown paragraphs only — no headings, no bullet lists, no preamble."
    )

    llm_prose = llm_call(prompt, max_tokens=700)

    if llm_prose:
        body = llm_prose
    else:
        # Template fallback
        rows = []
        for name, obs in regions_data:
            if obs:
                ws = obs.get("wind_speed")
                wd = obs.get("wind_dir")
                rows.append(
                    f"**{name}:** wind {ws} m/s ({_beaufort(ws)} Bft) "
                    f"from {_wind_dir_label(wd)} — {_sea_state(ws)}."
                )
            else:
                rows.append(f"**{name}:** observation data temporarily unavailable.")
        body = (
            f"Marine conditions across the Baltic Sea on {weekday}:\n\n"
            + "\n\n".join(rows)
        )

    body += (
        "\n\n---\n\n"
        "*Weather data: [SMHI Open Data](https://www.smhi.se/data) "
        "(CC BY 4.0 — Swedish Meteorological and Hydrological Institute). "
        "For indicative planning purposes only. Always consult official NAVTEX "
        "and national met office warnings before departure.*"
    )
    return title, description, body


def run_weather(seen):
    date = today_iso()
    slug = f"baltic-sea-weather-{date}"
    if slug in seen:
        print(f"[weather] already posted today ({slug}), skipping.")
        return seen

    print("[weather] fetching SMHI data …")
    regions_data = []
    for name, lat, lon in WEATHER_REGIONS:
        obs = fetch_smhi_marine(lat, lon)
        regions_data.append((name, obs))
        status = f"wind {obs.get('wind_speed')} m/s" if obs else "no data"
        print(f"  {name}: {status}")

    # Only skip if ALL regions failed
    if all(obs is None for _, obs in regions_data):
        print("[weather] all SMHI fetches failed, skipping.")
        return seen

    title, description, body = build_weather_article(regions_data, date)
    write_post(slug, title, date, description, "BalticDryIndex.com", body)
    seen.add(slug)
    return seen


# ── 3. EMSA SHIPPING POLICY NEWS ─────────────────────────────────────────────

def fetch_emsa_items():
    """Fetch EMSA press releases RSS. Returns list of {title, link, date, summary}."""
    raw = fetch_url(EMSA_RSS)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
        ns   = {"dc": "http://purl.org/dc/elements/1.1/"}
        items = []
        for item in root.iter("item"):
            title   = (item.findtext("title") or "").strip()
            link    = (item.findtext("link") or "").strip()
            desc    = (item.findtext("description") or "").strip()
            pub     = (item.findtext("pubDate") or "").strip()
            # Parse pub date to ISO
            try:
                dt = datetime.datetime.strptime(pub[:16], "%a, %d %b %Y")
                iso_date = dt.date().isoformat()
            except Exception:
                iso_date = today_iso()
            items.append({"title": title, "link": link, "summary": desc, "date": iso_date})
        return items
    except Exception as e:
        print(f"  EMSA RSS parse error: {e}")
        return []


def rewrite_emsa(item):
    """Rewrite an EMSA item as original prose. Returns (title, description, body) or None."""
    if not OPENROUTER_KEY:
        return None

    prompt = (
        "You are a maritime news editor for BalticDryIndex.com. "
        "Rewrite the following shipping safety/policy item in your own original words. "
        "Do not copy any phrases from the source text. Do not add facts not present in the source. "
        "Keep it factual, professional and concise.\n\n"
        f"SOURCE TITLE: {item['title']}\n"
        f"SOURCE SUMMARY: {item['summary']}\n"
        f"SOURCE URL: {item['link']}\n\n"
        "Write:\n"
        "1. A new headline (one line, under 90 characters)\n"
        "2. A one-sentence description for search engines (under 160 characters)\n"
        "3. 3–4 short paragraphs of body text (~200–250 words)\n\n"
        "Format your response EXACTLY as:\n"
        "HEADLINE: <headline here>\n"
        "DESCRIPTION: <description here>\n"
        "BODY:\n<body paragraphs in plain Markdown>\n"
    )

    text = llm_call(prompt, max_tokens=800)
    if not text:
        return None

    try:
        headline_m = re.search(r"HEADLINE:\s*(.+)", text)
        desc_m     = re.search(r"DESCRIPTION:\s*(.+)", text)
        body_m     = re.search(r"BODY:\s*\n(.*)", text, re.DOTALL)
        if not (headline_m and desc_m and body_m):
            return None
        headline = headline_m.group(1).strip().strip('"')
        desc     = desc_m.group(1).strip().strip('"')
        body     = body_m.group(1).strip()
        body    += (
            f"\n\n---\n\n"
            f"*Source: [EMSA — European Maritime Safety Agency]({item['link']}). "
            f"Rewritten in original language. EU open policy — attribution required.*"
        )
        return headline, desc, body
    except Exception as e:
        print(f"  EMSA rewrite parse error: {e}")
        return None


def run_emsa(seen):
    if not OPENROUTER_KEY:
        print("[EMSA] no OPENROUTER_API_KEY set, skipping policy news.")
        return seen

    print("[EMSA] fetching press releases …")
    items = fetch_emsa_items()
    if not items:
        print("[EMSA] no items fetched.")
        return seen

    cutoff = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    new_items = [i for i in items if i["date"] >= cutoff]
    print(f"[EMSA] {len(new_items)} items within last 7 days")

    written = 0
    for item in new_items:
        if written >= 2:
            break
        slug = "emsa-" + slugify(item["title"])
        if slug in seen:
            continue

        result = rewrite_emsa(item)
        if not result:
            continue

        title, description, body = result
        write_post(slug, title, item["date"], description, "BalticDryIndex.com", body)
        seen.add(slug)
        written += 1

    print(f"[EMSA] wrote {written} new article(s)")
    return seen


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    seen = load_seen()
    print(f"autopost_news: {today_iso()}, {len(seen)} slugs seen so far")

    seen = run_bdi_brief(seen)
    seen = run_weather(seen)
    seen = run_emsa(seen)

    save_seen(seen)
    print("autopost_news: done.")


if __name__ == "__main__":
    main()
