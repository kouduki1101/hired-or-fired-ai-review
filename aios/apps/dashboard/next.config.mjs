/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  env: {
    NEXT_PUBLIC_AIOS_API: process.env.NEXT_PUBLIC_AIOS_API ?? "http://localhost:8080",
  },
};

export default nextConfig;
