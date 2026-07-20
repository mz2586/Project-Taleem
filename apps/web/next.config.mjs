/** @type {import('next').NextConfig} */
// Mobile-first PWA, Server Components by default, minimal client JS (docs/17, 04-NFR DATA-01).
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Security headers (docs/13 §4). CSP tightened when asset origins are finalized.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
