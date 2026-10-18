// BalticDryIndex — MCP server (Model Context Protocol) at /mcp.
//
// Streamable-HTTP transport: agents POST JSON-RPC 2.0. Exposes the same
// capabilities as the REST API as discoverable MCP tools:
//   FREE : bdi_latest
//   PAID : bdi_signals, bdi_forecast, bdi_brief,
//          shipping_tce, shipping_voyage, shipping_freight_estimate,
//          shipping_bunker, shipping_distance, shipping_co2
//
// Monetisation for MCP callers is the subscription lane: send a valid key as
// the X-API-Key header (validated against the API_KEYS KV namespace). Agents
// that prefer per-call x402 micropayments use the REST endpoints under /v1,
// which are x402-gated; a paid MCP call without a key returns a clear pointer
// to that REST endpoint and its price.

import { normaliseHistory, computeSignals, computeForecast, computeBrief } from "../lib/bdi-compute.js";
import { calcDistance, calcBunker, calcTCE, calcFreightEstimate, calcVoyage, calcCO2 } from "../lib/shipping.js";

const SERVER_INFO = { name: "balticdryindex", version: "1.0.0" };
const PROTOCOL_VERSION = "2025-06-18";

async function readJson(origin, path) {
  const r = await fetch(origin + path, { cf: { cacheTtl: 300, cacheEverything: true } });
  if (!r.ok) throw new Error(`could not read ${path} (${r.status})`);
  return r.json();
}

// ── Tool catalogue ─────────────────────────────────────────────────────────
const num = { type: "number" };
const str = { type: "string" };
const ROUTE_HINT = "Known route key (e.g. tubarao-qingdao) or use distance_nm.";

const TOOLS = {
  bdi_latest: {
    paid: false,
    def: { description: "Latest Baltic Dry Index (BDI) headline value, change and date. Free.",
      inputSchema: { type: "object", properties: {} } },
    run: async (origin) => {
      const d = await readJson(origin, "/data/latest.json");
      return { index: "BDI", value: d.bdi.value, change: d.bdi.change, pct: d.bdi.pct, date: d.date,
        source: "Baltic Exchange", attribution: "Value © Baltic Exchange. Served by BalticDryIndex.com." };
    },
  },
  bdi_signals: {
    paid: true, rest: "/v1/signals", price: "$0.01",
    def: { description: "Derived BDI indicators: trend, momentum z-score, volatility, regime, distance from ATH.",
      inputSchema: { type: "object", properties: {} } },
    run: async (origin) => {
      const [hist, latest] = await Promise.all([readJson(origin, "/data/history.json"), readJson(origin, "/data/latest.json")]);
      return computeSignals(normaliseHistory(hist), latest.stats || {});
    },
  },
  bdi_forecast: {
    paid: true, rest: "/v1/forecast", price: "$0.05",
    def: { description: "BDI directional forecast with confidence band.",
      inputSchema: { type: "object", properties: { horizon: { ...num, description: "Days ahead, 1-30 (default 7)." } } } },
    run: async (origin, args) => {
      const horizon = Math.min(30, Math.max(1, parseInt(args.horizon || 7, 10)));
      const hist = await readJson(origin, "/data/history.json");
      return computeForecast(normaliseHistory(hist), horizon);
    },
  },
  bdi_brief: {
    paid: true, rest: "/v1/brief", price: "$0.02",
    def: { description: "Machine-readable BDI market brief: summary, drivers, streaks, per-vessel notes.",
      inputSchema: { type: "object", properties: {} } },
    run: async (origin) => {
      const [hist, latest] = await Promise.all([readJson(origin, "/data/history.json"), readJson(origin, "/data/latest.json")]);
      const series = normaliseHistory(hist);
      return computeBrief(latest, series, computeSignals(series, latest.stats || {}));
    },
  },
  shipping_tce: {
    paid: true, rest: "/v1/tce", price: "$0.03",
    def: { description: "Time Charter Equivalent ($/day) for a dry-bulk voyage.",
      inputSchema: { type: "object", required: ["freight_rate_usd_per_t"], properties: {
        vessel: str, route: { ...str, description: ROUTE_HINT }, distance_nm: num, speed_kn: num,
        freight_rate_usd_per_t: num, cargo_t: num, commission_pct: num, fuel_price_usd_per_t: num } } },
    run: (origin, a) => calcTCE(a),
  },
  shipping_voyage: {
    paid: true, rest: "/v1/voyage", price: "$0.05",
    def: { description: "Voyage P&L, breakeven freight rate and TCE for a dry-bulk voyage.",
      inputSchema: { type: "object", properties: {
        vessel: str, route: { ...str, description: ROUTE_HINT }, distance_nm: num, speed_kn: num,
        freight_rate_usd_per_t: num, cargo_t: num, commission_pct: num, fuel_price_usd_per_t: num } } },
    run: (origin, a) => calcVoyage(a),
  },
  shipping_freight_estimate: {
    paid: true, rest: "/v1/freight-estimate", price: "$0.03",
    def: { description: "Estimated cost to ship a bulk cargo ($/tonne and total).",
      inputSchema: { type: "object", properties: {
        vessel: str, route: { ...str, description: ROUTE_HINT }, distance_nm: num, speed_kn: num,
        commodity: str, cargo_t: num, daily_hire_usd: num, fuel_price_usd_per_t: num } } },
    run: (origin, a) => calcFreightEstimate(a),
  },
  shipping_bunker: {
    paid: true, rest: "/v1/bunker", price: "$0.02",
    def: { description: "Voyage bunker fuel tonnage and cost.",
      inputSchema: { type: "object", properties: {
        vessel: str, route: { ...str, description: ROUTE_HINT }, distance_nm: num, speed_kn: num,
        consumption_tpd: num, port_days: num, fuel_price_usd_per_t: num } } },
    run: (origin, a) => calcBunker(a),
  },
  shipping_distance: {
    paid: true, rest: "/v1/distance", price: "$0.01",
    def: { description: "Port-to-port distance and steaming days.",
      inputSchema: { type: "object", properties: {
        from: str, to: str, route: { ...str, description: ROUTE_HINT }, distance_nm: num, speed_kn: num } } },
    run: (origin, a) => calcDistance(a),
  },
  shipping_co2: {
    paid: true, rest: "/v1/co2", price: "$0.02",
    def: { description: "Voyage CO2 emissions and transport-work intensity.",
      inputSchema: { type: "object", properties: {
        vessel: str, route: { ...str, description: ROUTE_HINT }, distance_nm: num, speed_kn: num,
        fuel_tonnes: num, fuel_type: str, cargo_t: num } } },
    run: (origin, a) => calcCO2(a),
  },
};

function toolList() {
  return Object.entries(TOOLS).map(([name, t]) => ({
    name,
    description: t.paid ? `${t.def.description} [paid — ${t.price} via subscription key or ${t.rest} on x402]` : t.def.description,
    inputSchema: t.def.inputSchema,
  }));
}

async function hasValidKey(req, env) {
  const key = req.headers.get("X-API-Key");
  if (!key || !env || !env.API_KEYS) return false;
  try { return (await env.API_KEYS.get(`key:${key}`)) !== null; } catch { return false; }
}

const rpcResult = (id, result) => ({ jsonrpc: "2.0", id, result });
const rpcError = (id, code, message, data) => ({ jsonrpc: "2.0", id, error: { code, message, ...(data ? { data } : {}) } });

async function handleRpc(msg, req, env, origin) {
  const { id, method, params } = msg;
  switch (method) {
    case "initialize":
      return rpcResult(id, { protocolVersion: PROTOCOL_VERSION, capabilities: { tools: {} }, serverInfo: SERVER_INFO,
        instructions: "Baltic Dry Index data and dry-bulk shipping calculators. bdi_latest is free; other tools are paid via a subscription key (X-API-Key) or per-call x402 on the matching /v1 REST endpoint." });
    case "ping":
      return rpcResult(id, {});
    case "tools/list":
      return rpcResult(id, { tools: toolList() });
    case "tools/call": {
      const name = params && params.name;
      const args = (params && params.arguments) || {};
      const tool = TOOLS[name];
      if (!tool) return rpcError(id, -32602, `Unknown tool: ${name}`);
      if (tool.paid && !(await hasValidKey(req, env))) {
        return rpcResult(id, {
          isError: true,
          content: [{ type: "text", text: JSON.stringify({
            error: "payment_required",
            message: `'${name}' is a paid tool (${tool.price}). Provide a subscription key as the X-API-Key header, or call the REST endpoint ${tool.rest} which accepts x402 USDC micropayments.`,
            rest_endpoint: `https://www.balticdryindex.com${tool.rest}`,
            price: tool.price,
            docs: "https://www.balticdryindex.com/api/",
          }, null, 2) }],
        });
      }
      try {
        const data = await tool.run(origin, args);
        return rpcResult(id, { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] });
      } catch (e) {
        return rpcResult(id, { isError: true, content: [{ type: "text", text: JSON.stringify({ error: "tool_failed", message: String(e.message || e) }) }] });
      }
    }
    default:
      return rpcError(id, -32601, `Method not found: ${method}`);
  }
}

export async function onRequest(context) {
  const { request, env } = context;
  const origin = new URL(request.url).origin;

  // Discovery / health for a plain GET.
  if (request.method === "GET") {
    return Response.json({
      service: "BalticDryIndex MCP server",
      transport: "streamable-http (POST JSON-RPC 2.0)",
      endpoint: "/mcp",
      tools: Object.keys(TOOLS),
      docs: "https://www.balticdryindex.com/api/",
    });
  }
  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: { Allow: "GET, POST" } });
  }

  let body;
  try { body = await request.json(); }
  catch { return Response.json(rpcError(null, -32700, "Parse error"), { status: 400 }); }

  // Support batched requests; notifications (no id) get no response body.
  const msgs = Array.isArray(body) ? body : [body];
  const responses = [];
  for (const m of msgs) {
    if (m && m.id === undefined && typeof m.method === "string" && m.method.startsWith("notifications/")) continue;
    responses.push(await handleRpc(m, request, env, origin));
  }

  const headers = { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" };
  if (responses.length === 0) return new Response(null, { status: 202, headers });
  return new Response(JSON.stringify(Array.isArray(body) ? responses : responses[0]), { status: 200, headers });
}
