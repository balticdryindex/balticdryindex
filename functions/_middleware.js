// Cloudflare Pages middleware — runs on every request to the site.
// Injects the Google Analytics (gtag.js) tag into the <head> of every HTML
// page, including future auto-generated articles. Non-HTML responses
// (JSON, JS, CSS, images, the /v1 API) pass straight through untouched.

const GA_ID = "G-39SR36KVRP";

const GA_SNIPPET =
  `<script async src="https://www.googletagmanager.com/gtag/js?id=${GA_ID}"></script>` +
  `<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}` +
  `gtag('js',new Date());gtag('config','${GA_ID}');</script>`;

class HeadInjector {
  element(element) {
    // append = place it just before </head>
    element.append(GA_SNIPPET, { html: true });
  }
}

export async function onRequest(context) {
  const response = await context.next();

  // Only touch HTML documents.
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("text/html")) return response;

  return new HTMLRewriter()
    .on("head", new HeadInjector())
    .transform(response);
}
