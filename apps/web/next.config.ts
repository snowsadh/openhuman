import type { NextConfig } from "next";

const apiOrigin =
  process.env.OPENHUMAN_API_ORIGIN ??
  "https://openhuman-api.zopcloud.zop.dev";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    viewTransition: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
