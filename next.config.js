/** @type {import('next').NextConfig} */
const nextConfig = {
  // ── Server-only packages ────────────────────────────────────────────────
  // These are native Node.js modules used only in API routes (server-side).
  // Telling webpack to ignore them prevents "module not found" errors when
  // Next.js bundles the client-side code.
  serverExternalPackages: ["serialport", "@serialport/parser-readline"],

  // ── Webpack: ignore Node built-ins on the client ────────────────────────
  webpack(config, { isServer }) {
    if (!isServer) {
      // Prevent webpack from bundling Node.js built-ins into the browser bundle
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs:             false,
        path:           false,
        os:             false,
        child_process:  false,
        serialport:     false,
        "@serialport/parser-readline": false,
      };
    }
    return config;
  },
};

module.exports = nextConfig;
