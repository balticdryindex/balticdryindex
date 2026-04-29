# BalticDryIndex.com

Live Baltic Dry Index data website with automated daily updates.

## Architecture

- **Frontend**: Static HTML/CSS/JS hosted on Netlify
- **Data**: `/data/latest.json` updated daily by GitHub Actions
- **Blog**: Daily articles auto-generated in `/news/`
- **No server needed**: Pure static site, zero runtime cost

## Setup Instructions

### Step 1: Create GitHub Repository

1. Go to github.com → New repository
2. Name it: `balticdryindex`
3. Set to **Public** (required for free GitHub Actions)
4. Upload the contents of this zip (not the zip itself, the files inside `bdi-site/`)

### Step 2: Connect Netlify to GitHub

1. Go to netlify.com → Add new site → **Import from Git**
2. Choose GitHub → select `balticdryindex` repo
3. Build settings:
   - Build command: (leave empty)
   - Publish directory: `.`
4. Click Deploy
5. Add custom domain: `balticdryindex.com`

### Step 3: Enable Auto-Deploy from GitHub Actions

In your GitHub repo:
1. Go to Settings → Actions → General
2. Set "Workflow permissions" to **Read and write permissions**
3. Check "Allow GitHub Actions to create and approve pull requests"

The workflow in `.github/workflows/daily-update.yml` will:
- Run every weekday at 14:00 UTC (after Baltic Exchange publishes)
- Fetch BDI data from HandyBulk → Yahoo Finance → Stooq (in order)
- Update `/data/latest.json`
- Generate a daily blog post in `/news/`
- Commit changes → triggers Netlify auto-deploy

### Step 4: Test the Workflow

In GitHub → Actions tab → "Daily BDI Update" → "Run workflow" → Run

Check that `/data/latest.json` gets updated and a new post appears in `/news/`.

## File Structure

```
/
├── index.html              # Homepage
├── data/
│   └── latest.json         # Updated daily by GitHub Actions ← KEY FILE
├── news/
│   └── [slug]/index.html   # Auto-generated daily blog posts
├── scripts/
│   └── update_bdi.py       # Data fetcher + blog generator
├── .github/
│   └── workflows/
│       └── daily-update.yml # GitHub Actions schedule
├── assets/
│   ├── bdi.js              # Frontend reads /data/latest.json
│   └── style.css
├── what-is-the-baltic-dry-index/
├── bdi-chart-historical-data/
├── vessel-classes/
├── shipping-stocks/
├── analysis/
├── glossary/
├── about/
├── contact/
├── privacy-policy/
├── disclaimer/
├── zh/                     # Chinese
├── ja/                     # Japanese
├── pt/                     # Portuguese/Brazilian
├── ru/                     # Russian
├── ads.txt                 # Google AdSense
├── sitemap.xml
├── robots.txt
└── netlify.toml
```

## Data Sources (in priority order)

1. **HandyBulk.com** - Most reliable, scrapes Baltic Exchange daily report
2. **Yahoo Finance ^BDIY** - Good fallback, direct API
3. **Stooq.com** - Secondary fallback CSV
4. **Previous day values** - Used if all sources fail (never freezes site)

## Affiliate Links

- Dukascopy: `https://dukascopy.bank/swiss/open-mca-account/?ref=YJM-PUE&lang=en`
- IBKR: `https://ibkr.com/referral/julio411`

## AdSense

Publisher ID: `ca-pub-9696700979125307`
ads.txt: `google.com, pub-9696700979125307, DIRECT, f08c47fec0942fa0`

## Contact

balticdryindex@protonmail.com
Sea Blast LTD, Cane Garden, Kingstown, St. Vincent and the Grenadines, VC0100
