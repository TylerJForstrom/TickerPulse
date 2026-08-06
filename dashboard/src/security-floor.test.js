// Security floor for the npm tree.
//
// 2026-08-06: ten Dependabot alerts sat open on dashboard/package-lock.json
// because .github/dependabot.yml only watched pip and github-actions. The
// config gap is fixed, but nothing stopped a future lockfile edit — a
// resolution churn, a `npm audit fix --force` that "fixes" react-router by
// DOWNGRADING it (npm actively suggests 7.11.0, which is below the 7.18.0
// patch line), or a hand-rolled revert — from silently dropping back under
// a patched version.
//
// This test pins the advisory thresholds themselves, so a regression fails
// the build instead of waiting for Dependabot to re-notice it. Raise a floor
// here only when the corresponding advisory is genuinely superseded.
import { describe, expect, it } from "vitest";

import lock from "../package-lock.json";

// package name -> [minimum safe version, advisory that set the floor]
const FLOORS = {
  vitest: ["3.2.6", "GHSA-5xrq-8626-4rwp (critical)"],
  vite: ["6.4.3", "GHSA-fx2h-pf6j-xcff / GHSA-v6wh-96g9-6wx3 / GHSA-4w7w-66w2-5vf9"],
  esbuild: ["0.25.0", "GHSA-67mh-4wv8-2f99"],
  postcss: ["8.5.23", "GHSA-r28c-9q8g-f849 / GHSA-fxqj-rqcc-2cmp"],
  "react-router": ["7.18.0", "GHSA-wrjc-x8rr-h8h6 / GHSA-337j-9hxr-rhxg"],
  "react-router-dom": ["7.18.0", "GHSA-jjmj-jmhj-qwj2 (no fix on the 6.x line)"],
};

function compare(a, b) {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < 3; i += 1) {
    if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) - (pb[i] || 0);
  }
  return 0;
}

// Every install path counts, not just the top-level one: npm is free to nest
// a second, older copy of a transitive package under another dependency.
function installedVersions(name) {
  const suffix = `node_modules/${name}`;
  return Object.entries(lock.packages)
    .filter(([path]) => path === suffix || path.endsWith(`/${suffix}`))
    .map(([path, meta]) => [path, meta.version])
    .filter(([, version]) => typeof version === "string");
}

describe("package-lock security floors", () => {
  it("resolves the lockfile schema it was written against", () => {
    expect(lock.lockfileVersion).toBeGreaterThanOrEqual(3);
  });

  for (const [name, [floor, advisory]] of Object.entries(FLOORS)) {
    it(`keeps every ${name} at >= ${floor} — ${advisory}`, () => {
      const found = installedVersions(name);
      // If the package leaves the tree entirely there is nothing to protect;
      // a floor for an absent package must not fail the build.
      if (found.length === 0) return;
      for (const [path, version] of found) {
        expect(
          compare(version, floor),
          `${path} is ${version}, below the ${floor} floor for ${advisory}`,
        ).toBeGreaterThanOrEqual(0);
      }
    });
  }
});
