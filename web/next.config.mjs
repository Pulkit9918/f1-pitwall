/** @type {import('next').NextConfig} */
const config = {
  output: "export",          // a static site: `npm run build` writes ./out
  trailingSlash: true,       // /race/index.html, so any static host serves /race/ without extra settings
  images: { unoptimized: true },
};

export default config;
