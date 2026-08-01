import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../dist/web-smoke/", import.meta.url));
const port = Number(process.env.CAREPATH_DEMO_PORT ?? 4173);
const apiTarget = process.env.CAREPATH_DEMO_API ?? "http://127.0.0.1:8000";

const MIME = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
};

function safeFile(pathname) {
  const relative = normalize(pathname).replace(/^([./\\])+/, "");
  const candidate = join(root, relative || "index.html");
  if (!candidate.startsWith(root)) {
    return join(root, "index.html");
  }
  if (existsSync(candidate) && statSync(candidate).isFile()) {
    return candidate;
  }
  return join(root, "index.html");
}

const server = createServer(async (request, response) => {
  const requestUrl = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);
  if (requestUrl.pathname.startsWith("/api/")) {
    const target = `${apiTarget}${requestUrl.pathname.slice(4)}${requestUrl.search}`;
    const body = request.method === "GET" || request.method === "HEAD" ? undefined : request;
    try {
      const upstream = await fetch(target, {
        method: request.method,
        headers: {
          accept: request.headers.accept ?? "application/json",
          "content-type": request.headers["content-type"] ?? "application/json",
          "x-request-id": request.headers["x-request-id"] ?? "v08-browser-gate",
        },
        body,
        duplex: body ? "half" : undefined,
      });
      response.writeHead(upstream.status, Object.fromEntries(upstream.headers.entries()));
      response.end(Buffer.from(await upstream.arrayBuffer()));
    } catch (error) {
      response.writeHead(502, { "content-type": "application/json" });
      response.end(JSON.stringify({ error: String(error) }));
    }
    return;
  }

  const file = safeFile(decodeURIComponent(requestUrl.pathname));
  response.writeHead(200, { "content-type": MIME[extname(file)] ?? "application/octet-stream" });
  createReadStream(file).pipe(response);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`CarePath v0.8 demo server listening on http://127.0.0.1:${port}`);
});
