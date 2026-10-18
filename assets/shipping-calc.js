/* ───────────────────────────────────────────────────────────────────────
   BalticDryIndex.com — client-side dry-bulk shipping calculators.
   Same logic as the /v1 API (lib/shipping.js), ported to a browser global so
   the landing-page calculators run with no network call. Pure estimates.
   window.ShipCalc = { VESSELS, ROUTES, calcDistance, calcBunker, calcTCE,
                       calcFreight, calcVoyage, calcCO2 }
   ─────────────────────────────────────────────────────────────────────── */
(function () {
  const VESSELS = {
    handysize: { label: "Handysize", dwt: 35000,  speed: 13.5, sea_cons: 20, port_cons: 4,  port_da: 45000,  hire: 9000  },
    supramax:  { label: "Supramax",  dwt: 56000,  speed: 14,   sea_cons: 26, port_cons: 5,  port_da: 55000,  hire: 13000 },
    ultramax:  { label: "Ultramax",  dwt: 64000,  speed: 14,   sea_cons: 28, port_cons: 5,  port_da: 58000,  hire: 14000 },
    panamax:   { label: "Panamax",   dwt: 76000,  speed: 14,   sea_cons: 32, port_cons: 5,  port_da: 65000,  hire: 13500 },
    kamsarmax: { label: "Kamsarmax", dwt: 82000,  speed: 14,   sea_cons: 33, port_cons: 6,  port_da: 68000,  hire: 15000 },
    capesize:  { label: "Capesize",  dwt: 180000, speed: 14,   sea_cons: 55, port_cons: 8,  port_da: 110000, hire: 22000 },
  };

  const ROUTES = {
    "dampier-qingdao":         { nm: 3500,  label: "Dampier → Qingdao (iron ore)",        vessel: "capesize" },
    "tubarao-qingdao":         { nm: 11067, label: "Tubarão → Qingdao (iron ore)",        vessel: "capesize" },
    "tubarao-rotterdam":       { nm: 5100,  label: "Tubarão → Rotterdam (iron ore)",      vessel: "capesize" },
    "saldanha-qingdao":        { nm: 8900,  label: "Saldanha → Qingdao (iron ore)",       vessel: "capesize" },
    "newcastle-qingdao":       { nm: 4300,  label: "Newcastle → Qingdao (coal)",          vessel: "panamax"  },
    "richardsbay-rotterdam":   { nm: 7100,  label: "Richards Bay → Rotterdam (coal)",     vessel: "capesize" },
    "kalimantan-krishnapatnam":{ nm: 3000,  label: "Kalimantan → Krishnapatnam (coal)",   vessel: "supramax" },
    "usgulf-qingdao":          { nm: 11400, label: "US Gulf → Qingdao (grain)",           vessel: "panamax"  },
    "santos-qingdao":          { nm: 11500, label: "Santos → Qingdao (soybeans)",         vessel: "panamax"  },
    "santos-rotterdam":        { nm: 5600,  label: "Santos → Rotterdam (soybeans)",       vessel: "panamax"  },
    "vancouver-qingdao":       { nm: 5100,  label: "Vancouver → Qingdao (grain)",         vessel: "panamax"  },
  };

  const EMISSION = { vlsfo: 3.114, hfo: 3.114, mgo: 3.206, lng: 2.750 };
  const DEFAULT_FUEL = 600;
  const round = (n, d = 0) => { const p = 10 ** d; return Math.round(n * p) / p; };
  const num = (v, fb) => { const n = parseFloat(v); return isFinite(n) && n > 0 ? n : fb; };

  function distanceNm(p) {
    if (p.distance_nm) return { nm: num(p.distance_nm, 0), source: "user" };
    if (p.route && ROUTES[p.route]) return { nm: ROUTES[p.route].nm, source: "reference", label: ROUTES[p.route].label };
    return null;
  }

  function calcDistance(p) {
    const d = distanceNm(p); if (!d) return { error: "Pick a route or enter a distance." };
    const speed = num(p.speed_kn, 14);
    return { distance_nm: d.nm, speed_kn: speed, sea_days: round(d.nm / (speed * 24), 2) };
  }

  function calcBunker(p) {
    const v = VESSELS[p.vessel] || VESSELS.panamax;
    const d = distanceNm(p); if (!d) return { error: "Pick a route or enter a distance." };
    const speed = num(p.speed_kn, v.speed);
    const base = num(p.consumption_tpd, v.sea_cons);
    const adj = base * Math.pow(speed / v.speed, 3);
    const sea_days = d.nm / (speed * 24);
    const port_days = num(p.port_days, 6);
    const price = num(p.fuel_price, DEFAULT_FUEL);
    const sea_fuel = adj * sea_days, port_fuel = v.port_cons * port_days;
    const total = sea_fuel + port_fuel;
    return {
      vessel: v.label, distance_nm: d.nm, speed_kn: speed, sea_days: round(sea_days, 2),
      consumption_tpd: round(adj, 1), sea_fuel_t: round(sea_fuel, 1), port_fuel_t: round(port_fuel, 1),
      total_fuel_t: round(total, 1), fuel_price: price, fuel_cost_usd: round(total * price),
    };
  }

  function core(p) {
    const v = VESSELS[p.vessel] || VESSELS.panamax;
    const d = distanceNm(p); if (!d) return { error: "Pick a route or enter a distance." };
    const speed = num(p.speed_kn, v.speed);
    const load = num(p.load_days, 3), disch = num(p.disch_days, 3);
    const port_days = load + disch;
    const bunker = calcBunker({ ...p, vessel: p.vessel, speed_kn: speed, port_days });
    const sea_days = d.nm / (speed * 24);
    const voyage_days = sea_days + port_days;
    const cargo = num(p.cargo_t, Math.round(v.dwt * 0.95));
    const port_costs = num(p.port_costs, v.port_da);
    return { v, d, speed, sea_days, port_days, voyage_days, bunker, cargo, port_costs };
  }

  function calcTCE(p) {
    const c = core(p); if (c.error) return c;
    const rate = num(p.freight_rate, 0);
    if (!rate) return { error: "Enter a freight rate ($/tonne) to calculate TCE." };
    const comm = num(p.commission, 0);
    const gross = rate * c.cargo;
    const net = gross * (1 - comm / 100);
    const costs = c.bunker.fuel_cost_usd + c.port_costs + num(p.canal, 0);
    return {
      tce_usd_per_day: round((net - costs) / c.voyage_days),
      voyage_days: round(c.voyage_days, 2), cargo_t: c.cargo, freight_rate: rate,
      gross_revenue: round(gross), net_revenue: round(net), voyage_costs: round(costs),
      bunker_usd: c.bunker.fuel_cost_usd, port_usd: c.port_costs, vessel: c.v.label, distance_nm: c.d.nm,
    };
  }

  function calcFreight(p) {
    const c = core(p); if (c.error) return c;
    const hire = num(p.daily_hire, c.v.hire);
    const hire_cost = hire * c.voyage_days;
    const total = c.bunker.fuel_cost_usd + c.port_costs + hire_cost + num(p.canal, 0);
    return {
      cost_per_tonne: round(total / c.cargo, 2), total_cost: round(total),
      cargo_t: c.cargo, vessel: c.v.label, distance_nm: c.d.nm, voyage_days: round(c.voyage_days, 2),
      bunker_usd: c.bunker.fuel_cost_usd, port_usd: c.port_costs, hire_usd: round(hire_cost), daily_hire: hire,
    };
  }

  function calcVoyage(p) {
    const c = core(p); if (c.error) return c;
    const comm = num(p.commission, 0);
    const costs = c.bunker.fuel_cost_usd + c.port_costs + num(p.canal, 0);
    const breakeven = costs / (c.cargo * (1 - comm / 100));
    const out = {
      vessel: c.v.label, distance_nm: c.d.nm, cargo_t: c.cargo, voyage_days: round(c.voyage_days, 2),
      voyage_costs: round(costs), bunker_usd: c.bunker.fuel_cost_usd, port_usd: c.port_costs,
      breakeven_rate: round(breakeven, 2),
    };
    const rate = num(p.freight_rate, 0);
    if (rate) {
      const net = rate * c.cargo * (1 - comm / 100);
      out.freight_rate = rate; out.net_revenue = round(net);
      out.result = round(net - costs); out.tce_usd_per_day = round((net - costs) / c.voyage_days);
    }
    return out;
  }

  function calcCO2(p) {
    const factor = EMISSION[(p.fuel_type || "vlsfo").toLowerCase()] || EMISSION.vlsfo;
    let fuel = num(p.fuel_tonnes, 0), dist = num(p.distance_nm, 0), cargo = num(p.cargo_t, 0);
    if (!fuel) {
      const b = calcBunker(p); if (b.error) return b;
      fuel = b.total_fuel_t; dist = b.distance_nm;
      const c = core(p); if (!c.error) cargo = c.cargo;
    }
    const co2 = fuel * factor;
    const out = { co2_tonnes: round(co2, 1), fuel_tonnes: round(fuel, 1), fuel_type: (p.fuel_type || "vlsfo") };
    if (dist && cargo) out.g_co2_per_tonne_mile = round((co2 * 1e6) / (cargo * dist), 2);
    return out;
  }

  window.ShipCalc = { VESSELS, ROUTES, calcDistance, calcBunker, calcTCE, calcFreight, calcVoyage, calcCO2, round };
})();
