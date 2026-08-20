/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Compress dev bundles and pre-bundle popular packages so cold-start is
  // faster. Turbopack handles most of this; this just gives it hints.
  experimental: {
    optimizePackageImports: [
      "lucide-react",
      "@radix-ui/react-progress",
      "@radix-ui/react-dialog",
      "@radix-ui/react-tooltip",
      "date-fns",
    ],
  },
  // When the user accesses via port 3000 directly (not via nginx),
  // proxy /api/* AND top-level /health to the FastAPI backend on port 8003.
  // This makes port 3000 self-contained — works without nginx.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8003/api/:path*",
      },
      {
        // The settings page polls /health as a top-level path (not under /api/).
        // Without this rewrite, the frontend never reaches the backend and
        // the "服务状态" card stays stuck in a 404/loading state.
        source: "/health",
        destination: "http://127.0.0.1:8003/health",
      },
    ];
  },
};
module.exports = nextConfig;
