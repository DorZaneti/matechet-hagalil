/** @type {import('next').NextConfig} */
const securityHeaders = [
  // הקישור האישי מופיע בכתובת. no-referrer מונע ממנו לדלוף לאתרים חיצוניים דרך Referer.
  { key: "Referrer-Policy", value: "no-referrer" },
  // דפי לקוח לא אמורים להופיע במנועי חיפוש.
  { key: "X-Robots-Tag", value: "noindex, nofollow" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(self), geolocation=()" },
];

const nextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
