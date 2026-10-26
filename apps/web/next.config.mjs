/** @type {import('next').NextConfig} */
const API = process.env.INTERNAL_API_URL || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  // Compile the workspace TS contracts package.
  transpilePackages: ["@lighthouse/shared-types"],
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: false },
  // Same-origin proxy: the browser calls /api/* (so the refresh cookie is same-site and
  // works over http in dev); Next forwards to the FastAPI service.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
