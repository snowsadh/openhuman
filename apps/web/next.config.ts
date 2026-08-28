import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    viewTransition: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://openhuman-api:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
