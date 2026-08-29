// BalticDryIndex — derived analytics computed at request time.
// These are the PAID products. They are computed from the public raw history
// (facts) so the paid output never sits in a public file. Ported 1:1 from the
// Python logic in scripts/update_bdi.py so the site and API agree.

const ATTRIB =
  "Underlying BDI values \u00A9 Baltic Exchange. Analytics computed by BalticDryIndex.com.";
const DISCLAIM = "Indicative only. Not financial advice.";

// ── small numeric helpers ─────────────────────────────────────────────────
function sma(vals, n) {
  if (!vals.length) return null;
  const slice = vals.slice(-n);
  return Math.round((slice.reduce((a, b) => a + b, 0) / slice.length) * 10) / 10;
}
function stdev(vals) {
  if (vals.length < 2) return 0;
  const m = vals.reduce((a, b) => a + b, 0) / vals.length;
  return Math.sqrt(vals.reduce((a, b) => a + (b - m) ** 2, 0) / (vals.length - 1));
}
function trend(vals, n) {
  if (vals.length < Math.max(3, Math.floor(n / 2))) return "insufficient_data";
  const slice = vals.slice(-n);
  const s = slice.reduce((a, b) => a + b, 0) / slice.length;
  const diff = s ? (vals[vals.length - 1] - s) / s : 0;
  return diff > 0.01 ? "up" : diff < -0.01 ? "down" : "neutral";
}
function regime(vals) {
  if (vals.length < 20) return "insufficient_data";
  const short = vals.slice(-10).reduce((a, b) => a + b, 0) / 10;
  const longSlice = vals.slice(-40);
  const long = longSlice.reduce((a, b) => a + b, 0) / longSlice.length;
  if (short > long * 1.03) return "expansion";
  if (short < long * 0.97) return "contraction";
  return "range_bound";
}

// ── normalise history rows → [{date, bdi, bci, ...}] ──────────────────────
export function normaliseHistory(raw) {
  const rows = Array.isArray(raw) ? raw : raw.series || [];
  return rows
    .filter((r) => r && r.date && (r.bdi != null || r.value != null))
    .map((r) => ({
      date: r.date,
      bdi: r.bdi != null ? r.bdi : r.value,
      bci: r.bci, bpi: r.bpi, bsi: r.bsi, bhsi: r.bhsi,
    }));
}

// ── SIGNALS ───────────────────────────────────────────────────────────────
export function computeSignals(series, stats = {}) {
  const vals = series.map((r) => r.bdi);
  const dates = series.map((r) => r.date);
  const n = vals.length;
  const ath = stats.allTimeHigh || (vals.length ? Math.max(...vals) : null);

  const rets = [];
  for (let i = 1; i < n; i++) if (vals[i - 1]) rets.push((vals[i] - vals[i - 1]) / vals[i - 1]);
  const volAnnual = rets.length >= 5 ? Math.round(stdev(rets) * Math.sqrt(252) * 1000) / 1000 : null;

  const win = n >= 10 ? vals.slice(-90) : vals;
  let z = null;
  if (win.length >= 10) {
    const sd = stdev(win);
    const mean = win.reduce((a, b) => a + b, 0) / win.length;
    z = sd ? Math.round(((vals[n - 1] - mean) / sd) * 100) / 100 : 0;
  }

  return {
    date: dates[n - 1] || null,
    points_available: n,
    sma: { "7d": sma(vals, 7), "30d": sma(vals, 30), "90d": sma(vals, 90), "200d": sma(vals, 200) },
    trend: { "30d": trend(vals, 30), "90d": trend(vals, 90) },
    momentum_z: z,
    volatility_annualized: volAnnual,
    pct_from_ath: ath && n ? Math.round(((vals[n - 1] - ath) / ath) * 1000) / 10 : null,
    regime: regime(vals),
    note: n >= 30 ? null : "History is still building; indicators stabilise after ~30 trading days.",
    attribution: ATTRIB,
    disclaimer: DISCLAIM,
  };
}

// ── FORECAST (damped-drift baseline) ──────────────────────────────────────
export function computeForecast(series, horizon = 7) {
  const vals = series.map((r) => r.bdi);
  const n = vals.length;
  if (n < 10) {
    return { horizon_days: horizon, available: false,
      note: `Need ~10 trading days of history to forecast; have ${n}.`,
      disclaimer: "Model output, indicative only, not financial advice." };
  }
  const recent = vals.slice(-20);
  const drift = (recent[recent.length - 1] - recent[0]) / (recent.length - 1);
  let last = vals[n - 1], step = drift;
  const proj = [];
  for (let i = 0; i < horizon; i++) { last += step; proj.push(Math.round(last)); step *= 0.85; }
  const diffs = [];
  for (let i = 1; i < n; i++) diffs.push(vals[i] - vals[i - 1]);
  const band = Math.max(30, Math.round(stdev(diffs) * Math.sqrt(horizon)));
  const dir = proj[proj.length - 1] > vals[n - 1] ? "up" : proj[proj.length - 1] < vals[n - 1] ? "down" : "flat";
  return {
    horizon_days: horizon, available: true,
    as_of: series[n - 1].date, last_value: vals[n - 1],
    projection: proj, point: proj[proj.length - 1],
    band: [proj[proj.length - 1] - band, proj[proj.length - 1] + band],
    direction: dir, method: "damped-drift baseline",
    confidence: n < 60 ? "low" : "moderate",
    disclaimer: "Model output, indicative only, not financial advice.",
  };
}

// ── BRIEF (authored machine-readable summary) ─────────────────────────────
export function computeBrief(latest, series, signals) {
  const bdi = latest.bdi;
  const movers = { capesize: latest.bci, panamax: latest.bpi, supramax: latest.bsi, handysize: latest.bhsi };
  let lead = ["capesize", movers.capesize];
  for (const [k, v] of Object.entries(movers)) if (Math.abs(v.pct) > Math.abs(lead[1].pct)) lead = [k, v];

  const vals = series.map((r) => r.bdi);
  let streak = 0;
  for (let i = vals.length - 1; i > 0; i--) {
    const s = vals[i] > vals[i - 1] ? 1 : vals[i] < vals[i - 1] ? -1 : 0;
    if (streak === 0) streak = s;
    else if ((streak > 0 && s > 0) || (streak < 0 && s < 0)) streak += s;
    else break;
  }
  const events = [];
  if (Math.abs(streak) >= 2)
    events.push({ tag: "streak", detail: `${Math.abs(streak)} consecutive ${streak > 0 ? "gains" : "declines"}` });

  const dirw = bdi.change >= 0 ? "rose" : "fell";
  const cap = lead[0].charAt(0).toUpperCase() + lead[0].slice(1);
  const summary = `BDI ${dirw} ${Math.abs(bdi.change)} pts (${bdi.pct >= 0 ? "+" : ""}${bdi.pct.toFixed(2)}%) to ` +
    `${bdi.value.toLocaleString("en-US")} on ${latest.date}, led by ${cap}.`;

  const notes = {};
  for (const [k, v] of Object.entries(movers))
    notes[k] = v.change > 0 ? "leading" : v.change < 0 ? "soft" : "flat";

  return {
    date: latest.date, summary,
    drivers: [`${lead[0]}_${lead[1].change >= 0 ? "strength" : "weakness"}`],
    events, vessel_notes: notes, trend: signals.trend || {},
    attribution: "Underlying BDI values \u00A9 Baltic Exchange. Summary by BalticDryIndex.com.",
    disclaimer: DISCLAIM,
  };
}
