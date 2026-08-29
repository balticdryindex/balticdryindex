// BalticDryIndex — shipping calculators. Pure computation, no index data.
// All figures are transparent, overridable estimates. Reference tables use
// public, non-proprietary industry values. Every result carries a disclaimer.

const DISCLAIM = "Estimate only, based on the inputs and default assumptions shown. Not a firm quote.";

// ── Vessel classes (representative dry-bulk figures) ──────────────────────
// sea_cons/port_cons in tonnes/day VLSFO; port_da = typical total port charges
// for a laden voyage (both ends), USD; hire = representative TC $/day (VOLATILE —
// override with the current market rate).
export const VESSELS = {
  handysize: { dwt: 35000,  speed: 13.5, sea_cons: 20, port_cons: 4,  port_da: 45000,  hire: 9000  },
  supramax:  { dwt: 56000,  speed: 14,   sea_cons: 26, port_cons: 5,  port_da: 55000,  hire: 13000 },
  ultramax:  { dwt: 64000,  speed: 14,   sea_cons: 28, port_cons: 5,  port_da: 58000,  hire: 14000 },
  panamax:   { dwt: 76000,  speed: 14,   sea_cons: 32, port_cons: 5,  port_da: 65000,  hire: 13500 },
  kamsarmax: { dwt: 82000,  speed: 14,   sea_cons: 33, port_cons: 6,  port_da: 68000,  hire: 15000 },
  capesize:  { dwt: 180000, speed: 14,   sea_cons: 55, port_cons: 8,  port_da: 110000, hire: 22000 },
  vloc:      { dwt: 300000, speed: 14,   sea_cons: 70, port_cons: 10, port_da: 140000, hire: 28000 },
};

// ── Common dry-bulk routes (nautical miles, well-known public distances) ──
export const ROUTES = {
  "dampier-qingdao":          { nm: 3500,  commodity: "iron_ore", vessel: "capesize" },
  "porthedland-qingdao":      { nm: 3600,  commodity: "iron_ore", vessel: "capesize" },
  "tubarao-qingdao":          { nm: 11067, commodity: "iron_ore", vessel: "capesize" },
  "tubarao-rotterdam":        { nm: 5100,  commodity: "iron_ore", vessel: "capesize" },
  "saldanha-qingdao":         { nm: 8900,  commodity: "iron_ore", vessel: "capesize" },
  "newcastle-qingdao":        { nm: 4300,  commodity: "coal",     vessel: "panamax"  },
  "newcastle-kaohsiung":      { nm: 3900,  commodity: "coal",     vessel: "panamax"  },
  "richardsbay-rotterdam":    { nm: 7100,  commodity: "coal",     vessel: "capesize" },
  "puertobolivar-rotterdam":  { nm: 4900,  commodity: "coal",     vessel: "capesize" },
  "kalimantan-krishnapatnam": { nm: 3000,  commodity: "coal",     vessel: "supramax" },
  "usgulf-qingdao":           { nm: 11400, commodity: "grain",    vessel: "panamax"  },
  "santos-qingdao":           { nm: 11500, commodity: "soybeans", vessel: "panamax"  },
  "santos-rotterdam":         { nm: 5600,  commodity: "soybeans", vessel: "panamax"  },
  "vancouver-qingdao":        { nm: 5100,  commodity: "grain",    vessel: "panamax"  },
  "hamptonroads-rotterdam":   { nm: 3400,  commodity: "coal",     vessel: "capesize" },
};

// ── Commodities (stowage factor m³/t; typical vessel) ─────────────────────
export const COMMODITIES = {
  iron_ore:   { sf: 0.38, vessel: "capesize" },
  coal:       { sf: 1.30, vessel: "panamax"  },
  grain:      { sf: 1.30, vessel: "panamax"  },
  wheat:      { sf: 1.30, vessel: "panamax"  },
  soybeans:   { sf: 1.40, vessel: "panamax"  },
  bauxite:    { sf: 0.60, vessel: "capesize" },
  cement:     { sf: 0.72, vessel: "supramax" },
  steel:      { sf: 0.20, vessel: "supramax" },
  fertilizer: { sf: 1.10, vessel: "supramax" },
  sugar:      { sf: 1.10, vessel: "supramax" },
  scrap:      { sf: 0.50, vessel: "supramax" },
};

// ── Fuel CO2 emission factors (t CO2 per t fuel, IMO) ─────────────────────
export const EMISSION_FACTORS = { vlsfo: 3.114, hfo: 3.114, mgo: 3.206, mdo: 3.206, lng: 2.750 };

const DEFAULT_FUEL_PRICE = 600; // USD/t VLSFO — placeholder, override with market.
const round = (n, d = 0) => { const p = 10 ** d; return Math.round(n * p) / p; };

function resolveVessel(name) {
  if (!name) return { key: "panamax", ...VESSELS.panamax };
  const k = String(name).toLowerCase().replace(/[^a-z]/g, "");
  return VESSELS[k] ? { key: k, ...VESSELS[k] } : null;
}
function resolveDistance({ from, to, route, distance_nm }) {
  if (distance_nm) return { nm: Number(distance_nm), source: "user" };
  const key = route || (from && to ? `${from}-${to}`.toLowerCase().replace(/[^a-z-]/g, "") : null);
  if (key && ROUTES[key]) return { nm: ROUTES[key].nm, source: "reference", key };
  if (key) { const rev = key.split("-").reverse().join("-"); if (ROUTES[rev]) return { nm: ROUTES[rev].nm, source: "reference", key: rev }; }
  return null;
}

// ── /v1/distance ──────────────────────────────────────────────────────────
export function calcDistance(p) {
  const d = resolveDistance(p);
  if (!d) return { error: "unknown_route", message: "Route not in reference table. Pass distance_nm, or use a known route (see /api/).", known_routes: Object.keys(ROUTES) };
  const speed = Number(p.speed_kn) || 14;
  const sea_days = d.nm / (speed * 24);
  return { distance_nm: d.nm, distance_source: d.source, speed_kn: speed, sea_days: round(sea_days, 2), disclaimer: DISCLAIM };
}

// ── /v1/bunker ──────────────────────────────────────────────────────────────
export function calcBunker(p) {
  const v = resolveVessel(p.vessel);
  if (!v) return { error: "unknown_vessel", known: Object.keys(VESSELS) };
  const d = resolveDistance(p);
  if (!d) return { error: "unknown_route", known_routes: Object.keys(ROUTES) };
  const speed = Number(p.speed_kn) || v.speed;
  const base = Number(p.consumption_tpd) || v.sea_cons;
  const adj_cons = base * (speed / v.speed) ** 3;        // cube law vs class design speed
  const sea_days = d.nm / (speed * 24);
  const port_days = Number(p.port_days) || 6;
  const fuel_price = Number(p.fuel_price_usd_per_t) || DEFAULT_FUEL_PRICE;
  const sea_fuel = adj_cons * sea_days;
  const port_fuel = v.port_cons * port_days;
  const total_fuel = sea_fuel + port_fuel;
  return {
    vessel: v.key, distance_nm: d.nm, speed_kn: speed,
    sea_days: round(sea_days, 2), port_days,
    consumption_tpd_at_speed: round(adj_cons, 1),
    sea_fuel_t: round(sea_fuel, 1), port_fuel_t: round(port_fuel, 1),
    total_fuel_t: round(total_fuel, 1),
    fuel_price_usd_per_t: fuel_price,
    fuel_cost_usd: round(total_fuel * fuel_price),
    disclaimer: DISCLAIM,
  };
}

// shared voyage cost core
function voyageCore(p) {
  const v = resolveVessel(p.vessel);
  if (!v) return { error: "unknown_vessel", known: Object.keys(VESSELS) };
  const d = resolveDistance(p);
  if (!d) return { error: "unknown_route", known_routes: Object.keys(ROUTES) };
  const speed = Number(p.speed_kn) || v.speed;
  const load_days = Number(p.load_days) || 3;
  const disch_days = Number(p.disch_days) || 3;
  const port_days = load_days + disch_days;
  const bunker = calcBunker({ ...p, vessel: v.key, speed_kn: speed, port_days });
  const port_costs = Number(p.port_costs_usd) || v.port_da;
  const sea_days = d.nm / (speed * 24);
  const voyage_days = sea_days + port_days;
  const cargo_t = Number(p.cargo_t) || Math.round(v.dwt * 0.95);
  return { v, d, speed, sea_days, port_days, voyage_days, bunker, port_costs, cargo_t };
}

// ── /v1/tce — Time Charter Equivalent ────────────────────────────────────
export function calcTCE(p) {
  const c = voyageCore(p); if (c.error) return c;
  const freight_rate = Number(p.freight_rate_usd_per_t);
  if (!freight_rate) return { error: "missing_input", message: "freight_rate_usd_per_t is required for TCE." };
  const commission = Number(p.commission_pct) || 0;
  const gross = freight_rate * c.cargo_t;
  const net_revenue = gross * (1 - commission / 100);
  const voyage_costs = c.bunker.fuel_cost_usd + c.port_costs + (Number(p.canal_usd) || 0);
  const tce = (net_revenue - voyage_costs) / c.voyage_days;
  return {
    tce_usd_per_day: round(tce),
    voyage_days: round(c.voyage_days, 2),
    cargo_t: c.cargo_t, freight_rate_usd_per_t: freight_rate, commission_pct: commission,
    gross_revenue_usd: round(gross), net_revenue_usd: round(net_revenue),
    voyage_costs_usd: round(voyage_costs),
    cost_breakdown: { bunker_usd: c.bunker.fuel_cost_usd, port_usd: c.port_costs, canal_usd: Number(p.canal_usd) || 0 },
    vessel: c.v.key, distance_nm: c.d.nm,
    disclaimer: DISCLAIM,
  };
}

// ── /v1/freight-estimate — "cost to ship X" per tonne ────────────────────
export function calcFreightEstimate(p) {
  const c = voyageCore(p); if (c.error) return c;
  const daily_hire = Number(p.daily_hire_usd) || c.v.hire;
  const hire_cost = daily_hire * c.voyage_days;
  const total_cost = c.bunker.fuel_cost_usd + c.port_costs + hire_cost + (Number(p.canal_usd) || 0);
  const cost_per_tonne = total_cost / c.cargo_t;
  return {
    estimated_cost_per_tonne_usd: round(cost_per_tonne, 2),
    estimated_total_cost_usd: round(total_cost),
    cargo_t: c.cargo_t, vessel: c.v.key, distance_nm: c.d.nm,
    voyage_days: round(c.voyage_days, 2),
    cost_breakdown: { bunker_usd: c.bunker.fuel_cost_usd, port_usd: c.port_costs, hire_usd: round(hire_cost), canal_usd: Number(p.canal_usd) || 0 },
    assumptions: { daily_hire_usd: daily_hire, fuel_price_usd_per_t: c.bunker.fuel_price_usd_per_t, note: "daily_hire and fuel price are volatile — pass current values to refine." },
    disclaimer: DISCLAIM,
  };
}

// ── /v1/voyage — voyage P&L + breakeven ──────────────────────────────────
export function calcVoyage(p) {
  const c = voyageCore(p); if (c.error) return c;
  const freight_rate = Number(p.freight_rate_usd_per_t);
  const commission = Number(p.commission_pct) || 0;
  const voyage_costs = c.bunker.fuel_cost_usd + c.port_costs + (Number(p.canal_usd) || 0);
  const breakeven_rate = voyage_costs / (c.cargo_t * (1 - commission / 100));
  const out = {
    vessel: c.v.key, distance_nm: c.d.nm, cargo_t: c.cargo_t,
    voyage_days: round(c.voyage_days, 2),
    voyage_costs_usd: round(voyage_costs),
    cost_breakdown: { bunker_usd: c.bunker.fuel_cost_usd, port_usd: c.port_costs, canal_usd: Number(p.canal_usd) || 0 },
    breakeven_freight_rate_usd_per_t: round(breakeven_rate, 2),
    disclaimer: DISCLAIM,
  };
  if (freight_rate) {
    const net_revenue = freight_rate * c.cargo_t * (1 - commission / 100);
    const profit = net_revenue - voyage_costs;
    out.freight_rate_usd_per_t = freight_rate;
    out.net_revenue_usd = round(net_revenue);
    out.voyage_result_usd = round(profit);
    out.tce_usd_per_day = round(profit / c.voyage_days);
  } else {
    out.note = "Pass freight_rate_usd_per_t to also get revenue, P&L and TCE.";
  }
  return out;
}

// ── /v1/co2 — voyage CO2 + transport-work intensity ──────────────────────
export function calcCO2(p) {
  const fuel_type = String(p.fuel_type || "vlsfo").toLowerCase();
  const factor = EMISSION_FACTORS[fuel_type] || EMISSION_FACTORS.vlsfo;
  let fuel_t = Number(p.fuel_tonnes);
  let basis = "user_fuel_tonnes", distance_nm = Number(p.distance_nm) || null, cargo_t = Number(p.cargo_t) || null;
  if (!fuel_t) {
    const b = calcBunker(p); if (b.error) return b;
    fuel_t = b.total_fuel_t; basis = "computed_from_voyage"; distance_nm = b.distance_nm;
    const c = voyageCore(p); if (!c.error) cargo_t = c.cargo_t;
  }
  const co2_t = fuel_t * factor;
  const out = { co2_tonnes: round(co2_t, 1), fuel_tonnes: round(fuel_t, 1), fuel_type, emission_factor: factor, basis, disclaimer: DISCLAIM };
  if (distance_nm && cargo_t) out.intensity_g_co2_per_tonne_mile = round((co2_t * 1e6) / (cargo_t * distance_nm), 2);
  return out;
}
