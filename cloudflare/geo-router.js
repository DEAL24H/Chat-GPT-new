const ORIGIN = "https://deal24h.net";
const MANIFEST_URL = `${ORIGIN}/data/merchant-routes.json`;
const CACHE_TTL = 300;

function countryCode(request) {
  const country = request.cf && request.cf.country;
  return typeof country === "string" ? country.toUpperCase() : "";
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : "";
  } catch {
    return "";
  }
}

async function loadManifest() {
  const cache = caches.default;
  const cacheKey = new Request(MANIFEST_URL, { method: "GET" });
  const cached = await cache.match(cacheKey);
  if (cached) return cached.json();

  const response = await fetch(MANIFEST_URL, {
    cf: { cacheTtl: CACHE_TTL, cacheEverything: true },
  });
  if (!response.ok) throw new Error(`manifest ${response.status}`);

  const body = await response.text();
  const cachedResponse = new Response(body, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": `public, max-age=${CACHE_TTL}`,
    },
  });
  await cache.put(cacheKey, cachedResponse.clone());
  return JSON.parse(body);
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method !== "GET" && request.method !== "HEAD") {
      return fetch(request);
    }

    const match = url.pathname.match(/^\/go\/([A-Za-z0-9_-]+)\/?$/);
    if (!match) return fetch(request);

    try {
      const manifest = await loadManifest();
      const route = manifest?.routes?.[match[1]];
      if (!route) return new Response("Route not found", { status: 404 });

      const country = countryCode(request);
      const regional = safeUrl(route.regions?.[country]);
      const fallback = safeUrl(route.default);
      const target = regional || fallback;
      if (!target) return new Response("No verified merchant destination", { status: 404 });

      return Response.redirect(target, 302);
    } catch {
      return fetch(request);
    }
  },
};
