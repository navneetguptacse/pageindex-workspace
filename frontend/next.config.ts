import type { NextConfig } from "next"

const backend = (
  process.env.PAGEINDEX_BACKEND_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "")

const proxyBodyLimit =
  Number(process.env.PAGEINDEX_PROXY_BODY_LIMIT_MB ?? 202) * 1024 ** 2

if (!Number.isSafeInteger(proxyBodyLimit) || proxyBodyLimit < 1 * 1024 ** 2) {
  throw new Error("PAGEINDEX_PROXY_BODY_LIMIT_MB must be at least 1 MiB")
}

const nextConfig: NextConfig = {
  devIndicators: false,
  output: process.env.NEXT_OUTPUT_STANDALONE === "1" ? "standalone" : undefined,
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
    ]
  },
  experimental: {
    proxyClientMaxBodySize: proxyBodyLimit,
  },
}

export default nextConfig
