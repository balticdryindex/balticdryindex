// Cloudflare Pages middleware -- runs on every request to the site.
//
//  1. Injects the Google Analytics (gtag.js) tag into the <head> of every HTML page.
//  2. Places Adsterra ads on selected pages (see AD PLACEMENT). Because it is done
//     here, pages created later by the news / analysis generators carry ads too,
//     and no generated HTML has to be edited.
//  3. Shows a cookie-consent bar to visitors in the EU / EEA / UK / Switzerland and
//     only serves ads to them after they press Accept.
//
// Non-HTML responses (JSON, JS, CSS, images, the /v1 API) pass straight through.

// ── Analytics ────────────────────────────────────────────────────────────────
const GA_ID = "G-39SR36KVRP";
// false = analytics run for everyone (current behaviour).
// true  = EU/EEA/UK/CH visitors are only counted after they press Accept.
const GATE_ANALYTICS_BY_CONSENT = false;

const GA_SNIPPET =
  `<script async src="https://www.googletagmanager.com/gtag/js?id=${GA_ID}"></script>` +
  `<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}` +
  `gtag('js',new Date());gtag('config','${GA_ID}');</script>`;

// ── Adsterra snippets (exactly as issued in the Adsterra dashboard) ─────────
const RECT_300x250 =
  `<script>
  atOptions = {
    'key' : 'd51db8cb645c70706fdb65e952dfc7ac',
    'format' : 'iframe',
    'height' : 250,
    'width' : 300,
    'params' : {}
  };
</script>
<script data-cfasync="false" src="https://bauval.org/22/d51db8cb645c70706fdb65e952dfc7ac"></script>`;

const NATIVE_BANNER =
  `<script async fetchpriority="high" data-cfasync="false" src="https://bauval.org/21/4f0baff10488f9e527575abda4c687f0"></script>
<div id="container-4f0baff10488f9e527575abda4c687f0"></div>`;

function slot(inner, minHeight, maxWidth) {
  return (
    `<div class="ad-slot" style="margin:28px auto;text-align:center;max-width:${maxWidth};">` +
    `<div style="font:10px/1 monospace;letter-spacing:.08em;color:#888;margin-bottom:6px;">ADVERTISEMENT</div>` +
    `<div style="min-height:${minHeight}px;">${inner}</div></div>`
  );
}

// ── AD PLACEMENT ─────────────────────────────────────────────────────────────
//  homepage (+ the 7 translated homepages) : 300x250 at the bottom of the sidebar
//  /news/<post>/ and /analysis/<post>/      : native banner right after the article
//  nowhere else (tools, calculators, legal pages, admin, API stay ad-free)
const HOME_RE = /^\/(?:(?:zh|ja|es|fr|ar|pt|ru)\/)?$/;
const ARTICLE_RE = /^\/(?:news|analysis)\/[^/]+\/?$/;

// ── Consent ──────────────────────────────────────────────────────────────────
// Countries where ads/analytics cookies need prior consent: EU 27 + EEA + UK + CH.
const CONSENT_COUNTRIES = new Set([
  "AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE",
  "IS","LI","NO","GB","CH",
]);

function getCookie(request, name) {
  const m = (request.headers.get("cookie") || "").match(new RegExp("(?:^|;\\s*)" + name + "=([^;]*)"));
  return m ? m[1] : "";
}

const CONSENT_BAR =
  `<div id="bdi-consent" role="dialog" aria-label="Cookie consent" style="position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#10151c;color:#e8e8e8;border-top:1px solid #444;padding:14px 18px;font:13px/1.5 system-ui,sans-serif;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:center;">` +
  `<span style="max-width:760px;">We use cookies to show advertising and understand how the site is used. Choose whether to allow advertising cookies. ` +
  `<a href="/privacy-policy/" style="color:#e8c46a;">Privacy policy</a></span>` +
  `<span style="display:flex;gap:10px;">` +
  `<button id="bdi-no" style="padding:8px 18px;background:#10151c;color:#e8e8e8;border:1px solid #888;border-radius:4px;cursor:pointer;font:inherit;">Reject</button>` +
  `<button id="bdi-yes" style="padding:8px 18px;background:#10151c;color:#e8e8e8;border:1px solid #888;border-radius:4px;cursor:pointer;font:inherit;">Accept</button>` +
  `</span></div>` +
  `<script>(function(){function s(v){document.cookie='bdi_consent='+v+';max-age=31536000;path=/;SameSite=Lax';` +
  `var b=document.getElementById('bdi-consent');if(b)b.remove();if(v==='yes')location.reload();}` +
  `document.getElementById('bdi-yes').onclick=function(){s('yes')};` +
  `document.getElementById('bdi-no').onclick=function(){s('no')};})();</script>`;

class Append {
  constructor(html) { this.html = html; }
  element(el) { el.append(this.html, { html: true }); }
}
class Remove {
  element(el) { el.remove(); }
}
class After {
  constructor(html) { this.html = html; }
  element(el) { el.after(this.html, { html: true }); }
}

export async function onRequest(context) {
  const { request } = context;
  const response = await context.next();

  // Only touch HTML documents.
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("text/html")) return response;

  const path = new URL(request.url).pathname;
  const country = (request.cf && request.cf.country) || "";
  const needsConsent = CONSENT_COUNTRIES.has(country);
  const choice = getCookie(request, "bdi_consent"); // "yes" | "no" | ""
  const adsAllowed = needsConsent ? choice === "yes" : true;

  const rw = new HTMLRewriter();

  // Analytics
  const gaAllowed = GATE_ANALYTICS_BY_CONSENT && needsConsent ? choice === "yes" : true;
  if (gaAllowed) rw.on("head", new Append(GA_SNIPPET));

  // Existing Google AdSense loader on the pages: also held back until consent
  // is given where consent is required (keeps the cookie bar truthful).
  let modified = false;
  if (!adsAllowed) {
    rw.on('script[src*="pagead2.googlesyndication.com"]', new Remove());
    modified = true;
  }

  // Ads
  if (adsAllowed && !path.startsWith("/admin")) {
    if (HOME_RE.test(path)) {
      rw.on(".main-right", new Append(slot(RECT_300x250, 250, "300px")));
      modified = true;
    } else if (ARTICLE_RE.test(path)) {
      rw.on("article.prose", new After(slot(NATIVE_BANNER, 0, "720px")));
      modified = true;
    }
  }

  // Consent bar (only where consent is required and not yet given/refused)
  if (needsConsent && !choice) {
    rw.on("body", new Append(CONSENT_BAR));
    modified = true;
  }

  const out = rw.transform(response);
  if (modified || needsConsent) {
    // the HTML now depends on country + consent cookie -> keep caches honest
    const headers = new Headers(out.headers);
    headers.append("Vary", "Cookie");
    return new Response(out.body, { status: out.status, statusText: out.statusText, headers });
  }
  return out;
}
