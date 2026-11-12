import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const DEV_PORT = 5173;
const BACKEND = "http://localhost:8000";

/**
 * code-server (e.g. inside a Coder workspace) exposes forwarded ports under a path such as
 * https://coder.example.com/@user/ws.agent/apps/code-server/proxy/5173/ and advertises the
 * template in VSCODE_PROXY_URI. When it's set, the dev server runs under that path prefix.
 */
function codeServerProxy(): URL | undefined {
  const template = process.env.VSCODE_PROXY_URI;
  if (!template?.includes("{{port}}")) return undefined;
  return new URL(template.replace("{{port}}", String(DEV_PORT)));
}

/**
 * code-server's /proxy/<port>/ route strips the path prefix before forwarding, so requests reach
 * Vite without it. Put it back so Vite's base handling and the /api proxy match, and tell the app
 * (router + API client) which prefix it is served under.
 */
function servePrefixed(prefix: string): Plugin {
  return {
    name: "plantasaurus:code-server-prefix",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url && !req.url.startsWith(prefix)) req.url = prefix + req.url.replace(/^\//, "");
        next();
      });
    },
    transformIndexHtml: () => [
      { tag: "script", children: `window.__BASE_PATH__ = ${JSON.stringify(prefix)};`, injectTo: "head-prepend" },
    ],
  };
}

export default defineConfig(({ command }) => {
  const remote = command === "serve" ? codeServerProxy() : undefined;
  const prefix = remote?.pathname;

  return {
    // base: "./" keeps built asset URLs relative so the app works behind Home Assistant ingress.
    base: prefix ?? "./",
    plugins: [react(), ...(prefix ? [servePrefixed(prefix)] : [])],
    build: { chunkSizeWarningLimit: 1500 },
    server: {
      port: DEV_PORT,
      allowedHosts: remote ? [remote.hostname] : [],
      proxy: prefix
        ? { [`${prefix}api`]: { target: BACKEND, rewrite: (p) => p.slice(prefix.length - 1) } }
        : { "/api": BACKEND },
    },
  };
});
