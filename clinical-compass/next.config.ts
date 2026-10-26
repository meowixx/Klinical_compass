import type { NextConfig } from 'next';
const config: NextConfig = { distDir: process.env.NEXT_DIST_DIR || '.next', output: 'export', images: { unoptimized: true }, trailingSlash: true };
export default config;
