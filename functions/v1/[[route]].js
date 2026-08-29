// BalticDryIndex API — one Cloudflare Pages Function serving all of /v1/*.
//
//   FREE : GET /v1/latest                                  (BDI headline number)
//   PAID : GET /v1/signals  /v1/forecast  /v1/brief        (index analytics)
//          GET /v1/distance /v1/bunker /v1/tce             (shipping calculators)
//          GET /v1/freight-estimate /v1/voyage /v1/co2
//
// Paid analytics are COMPUTED from the public raw history so the product never
// sits in a downloadable file. Shipping calculators are pure computation.
// Each paid route: valid X-API-Key → free pass; otherwise x402 micropayment.

import { Hono } from "hono";
import { cors } from "hono/cors";
import { handle } from "hono/cloudflare-pages";
import { paymentMiddleware } from "x402-hono";
import { createFacilitatorConfig } from "@coinbase/x402";
import { normaliseHistory, computeSignals, computeForecast, computeBrief } from "../../lib/bdi-compute.js";
import { calcDistance, calcBunker, calcTCE, calcFreightEstimate, calcVoyage, calcCO2 } from "../../lib/shipping.js";

// ─────────────────────────────────────────────────────────────────────────
// CONFIG — the only lines you touch.
// ─────────────────────────────────────────────────────────────────────────
const PAY_TO_WALLET = "0xYOUR_WALLET_ADDRESS_HERE"; // ← your receiving address
const NETWORK       = "base";  // MAINNET. Use "base-sepolia" to test on free testnet.
// Mainnet ("base") settles real USDC via the Coinbase CDP facilitator and needs
// CDP_API_KEY_ID + CDP_API_KEY_SECRET set as Cloudflare environment variables.
// Testnet ("base-sepolia") uses the free public facilitator and needs no keys.
// ─────────────────────────────────────────────────────────────────────────

const app = new Hono();
app.use("*", cors({ origin: "*", allowMethods: ["GET", "OPTIONS"] }));

async function readJson(reqUrl, path) {
  const origin = new URL(reqUrl).origin;
  const r = await fetch(origin + path, { cf: { cacheTtl: 300, cacheEverything: true } });
  if (!r.ok) throw new Error(`could not read ${path} (${r.status})`);
  return r.json();
}
const q = (c) => c.req.query();

// ── PAID ROUTE TABLE: price, description, handler ─────────────────────────
const PAID = {
  // Index analytics (computed from public history)
  "/v1/signals": { price: "$0.01", desc: "BDI derived indicators (trend, momentum, volatility, regime)",
    h: async (c) => { const [hist, latest] = await Promise.all([readJson(c.req.url, "/data/history.json"), readJson(c.req.url, "/data/latest.json")]);
      return c.json(computeSignals(normaliseHistory(hist), latest.stats || {})); } },
  "/v1/forecast": { price: "$0.05", desc: "BDI directional forecast with confidence band",
    h: async (c) => { const horizon = Math.min(30, Math.max(1, parseInt(q(c).horizon || "7", 10)));
      const hist = await readJson(c.req.url, "/data/history.json"); return c.json(computeForecast(normaliseHistory(hist), horizon)); } },
  "/v1/brief": { price: "$0.02", desc: "BDI machine-readable market brief",
    h: async (c) => { const [hist, latest] = await Promise.all([readJson(c.req.url, "/data/history.json"), readJson(c.req.url, "/data/latest.json")]);
      const series = normaliseHistory(hist); return c.json(computeBrief(latest, series, computeSignals(series, latest.stats || {}))); } },

  // Shipping calculators (pure computation, no index data)
  "/v1/distance":        { price: "$0.01", desc: "Port-to-port distance and steaming days", h: (c) => c.json(calcDistance(q(c))) },
  "/v1/bunker":          { price: "$0.02", desc: "Voyage bunker fuel tonnage and cost",      h: (c) => c.json(calcBunker(q(c))) },
  "/v1/tce":             { price: "$0.03", desc: "Time Charter Equivalent ($/day)",          h: (c) => c.json(calcTCE(q(c))) },
  "/v1/freight-estimate":{ price: "$0.03", desc: "Estimated cost to ship a bulk cargo ($/t)", h: (c) => c.json(calcFreightEstimate(q(c))) },
  "/v1/voyage":          { price: "$0.05", desc: "Voyage P&L, breakeven rate and TCE",        h: (c) => c.json(calcVoyage(q(c))) },
  "/v1/co2":             { price: "$0.02", desc: "Voyage CO2 and transport-work intensity",   h: (c) => c.json(calcCO2(q(c))) },
};

const WALLET_OK = /^0x[a-fA-F0-9]{40}$/.test(PAY_TO_WALLET);
const TESTNET = NETWORK.endsWith("sepolia") || NETWORK.endsWith("devnet");
const ROUTE_CONFIG = Object.fromEntries(
  Object.entries(PAID).map(([p, v]) => [p, { price: v.price, network: NETWORK, config: { description: v.desc } }])
);

// The payment middleware is built lazily on the first request, because on
// Cloudflare the CDP credentials arrive via the request env (c.env), not at
// module load. Memoised thereafter. Returns null when not fully configured,
// so the free endpoint keeps working and paid routes answer cleanly.
let _x402 = null, _x402Built = false;
function getPayment(env) {
  if (_x402Built) return _x402;
  _x402Built = true;
  if (!WALLET_OK) return (_x402 = null);
  let facilitator;
  if (TESTNET) {
    facilitator = { url: "https://x402.org/facilitator" };          // free testnet
  } else {
    if (!env || !env.CDP_API_KEY_ID || !env.CDP_API_KEY_SECRET) {   // mainnet needs CDP keys
      _x402Built = false;                                           // retry once keys appear
      return null;
    }
    facilitator = createFacilitatorConfig(env.CDP_API_KEY_ID, env.CDP_API_KEY_SECRET);
  }
  return (_x402 = paymentMiddleware(PAY_TO_WALLET, ROUTE_CONFIG, facilitator));
}

async function hasValidKey(c) {
  const key = c.req.header("X-API-Key");
  if (!key || !c.env || !c.env.API_KEYS) return false;
  try { return (await c.env.API_KEYS.get(`key:${key}`)) !== null; } catch { return false; }
}
// Dual lane: valid API key → straight through; else enforce x402.
const gate = async (c, next) => {
  if (await hasValidKey(c)) { c.header("X-Access", "api-key"); return next(); }
  const x402 = getPayment(c.env);
  if (!x402) return c.json({
    error: "payment_not_configured",
    message: WALLET_OK
      ? "Mainnet requires CDP_API_KEY_ID and CDP_API_KEY_SECRET environment variables."
      : "Set PAY_TO_WALLET to your receiving address.",
  }, 503);
  return x402(c, next);
};

// Register every paid route with the gate + its handler.
for (const [path, v] of Object.entries(PAID)) { app.use(path, gate); app.get(path, v.h); }

// ── FREE ──────────────────────────────────────────────────────────────────
app.get("/v1/latest", async (c) => {
  try {
    const d = await readJson(c.req.url, "/data/latest.json");
    return c.json({
      index: "BDI", value: d.bdi.value, change: d.bdi.change, pct: d.bdi.pct, date: d.date,
      source: "Baltic Exchange",
      attribution: "Value \u00A9 Baltic Exchange. Served by BalticDryIndex.com.",
      paid_endpoints: Object.keys(PAID), docs: "/api/",
    }, 200, { "Cache-Control": "public, max-age=300" });
  } catch { return c.json({ error: "data_unavailable" }, 503); }
});

app.get("/v1", (c) => c.json({
  service: "BalticDryIndex API", free: ["/v1/latest"], paid: Object.keys(PAID),
  payment: "x402 (USDC) per call, or an X-API-Key subscription.", docs: "/api/",
}));
app.all("*", (c) => c.json({ error: "not_found", see: "/api/" }, 404));

export const onRequest = handle(app);
