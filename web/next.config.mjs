import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * `outputFileTracingRoot` is pinned to this directory because Next was resolving
 * the workspace root by walking up until it found a lockfile, and finding
 * `/Users/both/package-lock.json` - an unrelated file in the developer's home
 * directory. It said so on every build:
 *
 *   Warning: Next.js inferred your workspace root, but it may not be correct.
 *   We detected multiple lockfiles and selected the directory of
 *   /Users/both/package-lock.json as the root directory.
 *
 * File tracing decides which files ship in a standalone/serverless bundle. A
 * root that far up traces the wrong tree, and the failure surfaces at runtime as
 * a missing module in a deployed build rather than at build time here.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
