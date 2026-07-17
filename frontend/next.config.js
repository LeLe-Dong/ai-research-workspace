/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // When the user accesses via port 3000 directly (not via nginx),
  // proxy /api/* to the FastAPI backend on port 8003.
  // This makes port 3000 self-contained — works without nginx.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8003/api/:path*",
      },
    ];
  },
};
module.exports = nextConfig;
