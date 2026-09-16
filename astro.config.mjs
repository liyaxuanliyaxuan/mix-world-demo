import { defineConfig } from 'astro/config';

// Static output only. No SSR, no adapters, no analytics.
// Build variants (see package.json):
//   npm run build          -> dist/          (production semantics)
//   npm run build:review   -> dist-review/   (anonymous review preview, noindex)
//   npm run build:public   -> dist-public/   (public; unapproved modules hidden)
export default defineConfig({
  base: '/mix-world-demo',
  output: 'static',
  compressHTML: true,
});
