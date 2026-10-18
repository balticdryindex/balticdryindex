#!/usr/bin/env python3
"""
LLM-grounded auto-news enhancement for BalticDryIndex.com — OpenRouter edition.

Rewrites ONLY the prose paragraphs of a generated analysis article using real,
pinned numbers, via OpenRouter (OpenAI-compatible API). Every article then reads
differently instead of from a fixed template. Headline, stat boxes, schema, ads
and footer are left exactly as update_bdi.py produced them.

SAFE BY DESIGN: if OPENROUTER_API_KEY is not set, or the call fails for any
reason, enhance() returns the original HTML unchanged. The template is always the
fallback, so the weekly job can never break because of this.

Wiring (one line in update_bdi.py, weekly branch):

    import llm_news                                        # top imports
    ...
    slug, url_path, headline, excerpt, article_html = generate_article(data)
    article_html = llm_news.enhance(article_html, data)    # <-- add this line
    save_article(slug, article_html)

GitHub Actions secrets on the weekly workflow:
    OPENROUTER_API_KEY   (required to switch LLM mode on)
    OPENROUTER_MODEL     (optional; e.g. "anthropic/claude-sonnet-4.5",
                          "openai/gpt-4o-mini", "google/gemini-2.0-flash-001")
"""
import json
import os
import re
import urllib.request

MODEL    = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
API_KEY  = os.environ.get("OPENROUTER_API_KEY")
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

PROSE_RE = re.compile(r'(<article class="prose">)(.*?)(<p[^>]*>Source:)', re.DOTALL)


def _prompt(data):
    b = data["bdi"]; bc = data["bci"]; bp = data["bpi"]; bs = data["bsi"]; bh = data["bhsi"]
    def line(name, idx):
        return f'{name}: {idx["value"]:,} ({"+" if idx["change"]>=0 else ""}{idx["change"]} / {idx["pct"]:+.2f}%)'
    facts = "\n".join([
        f'Date: {data["date"]}',
        line("BDI (headline)", b),
        line("BCI Capesize", bc),
        line("BPI Panamax", bp),
        line("BSI Supramax", bs),
        line("BHSI Handysize", bh),
    ])
    return (
        "You are a dry bulk shipping market writer for BalticDryIndex.com. Write the body of a "
        "weekly Baltic Dry Index market wrap using ONLY these figures. Do not invent specific "
        "numbers, company names, routes, or quotes beyond what is given — you may refer in general "
        "terms to iron ore, coal and grain demand, Capesize/Panamax/Supramax/Handysize segments, "
        "and tonnage supply.\n\n"
        f"FIGURES:\n{facts}\n\n"
        "Write 4-5 short paragraphs (~280-360 words total). Open with the BDI move and what it "
        "signals, then cover Capesize, then Panamax and the smaller vessels, then a closing read on "
        "what the current level means. Use a neutral, professional market-report tone. "
        "Return ONLY an HTML fragment: <p>...</p> paragraphs, with optional <h2>...</h2> subheads. "
        "No markdown, no preamble, no <html> or <body> wrapper."
    )


def _call_api(prompt):
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        # Optional attribution headers OpenRouter uses for its dashboards:
        "HTTP-Referer": "https://www.balticdryindex.com",
        "X-Title": "BalticDryIndex Auto-News",
    })
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    text = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
    text = re.sub(r"^```(?:html)?\s*|\s*```$", "", text).strip()
    return text


def enhance(html, data):
    """Return html with prose paragraphs replaced by grounded LLM prose.
    Returns the input unchanged on any problem (no key, API error, bad shape)."""
    if not API_KEY:
        return html
    try:
        m = PROSE_RE.search(html)
        if not m:
            return html
        prose = _call_api(_prompt(data))
        if not prose or "<p" not in prose.lower():
            return html
        return html[:m.start()] + m.group(1) + "\n" + prose + "\n" + m.group(3) + html[m.end():]
    except Exception as e:
        print(f"llm_news: enhancement skipped ({e})")
        return html


if __name__ == "__main__":
    sample = ('<article class="prose">\n<p>OLD TEMPLATE PROSE</p>\n'
              '<p style="font">Source: Baltic Exchange</p></article>')
    data = {"date": "2026-10-18",
            "bdi": {"value": 2743, "change": -12, "pct": -0.44},
            "bci": {"value": 4100, "change": -20, "pct": -0.5},
            "bpi": {"value": 1900, "change": 5, "pct": 0.3},
            "bsi": {"value": 1500, "change": 0, "pct": 0.0},
            "bhsi": {"value": 800, "change": 2, "pct": 0.25}}
    out = enhance(sample, data)
    print("no-key fallback leaves html unchanged:", out == sample)
    print("endpoint:", ENDPOINT)
    print("default model:", MODEL)
