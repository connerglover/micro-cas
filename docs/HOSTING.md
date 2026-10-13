# Cloudflare Worker from GitHub

Use **cas.connerglover.com**, Worker **cas**, deployment branch **pages**.
The repository stays private. Setup is entirely in dash.cloudflare.com; local
Wrangler login and Cloudflare secrets in GitHub are not needed.

## Branches

- `main`: calculator and website source, tests, build tooling and documentation.
  The complete v1 history is merged here. Make future changes here or in feature
  branches merged into main.
- `pages`: generated deployment files only, with an independent history.
  `public/` contains the tested installer, calculator download, vendor code and
  license sources. The root contains the Worker config and deployment provenance.
- `v1`: retained for history; it no longer drives production publication.

After every successful main build, GitHub Actions updates pages with the exact
installer artifact from that run. Cloudflare watches pages and deploys it. A
failed build leaves the previous website intact. The publishing job needs only
GitHub's built-in token with contents-write permission; PRs and stale builds
cannot publish. Updates preserve history and never force push. Do not edit or
merge the generated pages branch into main.

## One-time dashboard setup

1. Open **Workers & Pages → Create application → Continue with GitHub**.
   Authorize the Cloudflare GitHub app for `connerglover/cas-evo` and select it.
   For an existing Worker, connect GitHub under **Settings → Builds** instead.
2. Configure:

   | Setting | Value |
   | --- | --- |
   | Worker name | `cas` |
   | Production branch | `pages` |
   | Root directory | Repository root (`/`) |
   | Build command | Leave empty |
   | Deploy command | `npx --yes wrangler@4.149.0 deploy` |
   | Builds for other branches | Disabled |

   Keep the root at the repository root so Wrangler finds its config; that
   config serves only `public/`. Cloudflare creates its deployment credential
   through the GitHub integration. All website files are already built.
3. Select **Deploy**. Check the installer at the generated workers.dev address.
4. Open **Settings → Domains & Routes → Add → Custom Domain**. Enter
   **cas.connerglover.com**, review the proposed DNS change, and confirm.
   Cloudflare creates the DNS record and HTTPS certificate. Preserve unrelated
   DNS records; the apex domain does not need to change.
5. Once active, open https://cas.connerglover.com in desktop Chrome or Edge.

The name pages refers to a Git branch; this setup deploys a Cloudflare Worker.
The earlier Pages Direct Upload job has been removed. Do not configure the old
CLOUDFLARE_API_TOKEN/CLOUDFLARE_ACCOUNT_ID GitHub settings for this setup, and do
not enable GitHub Pages. See [STATUS.md](STATUS.md) for what has actually been verified.

## Verification and maintenance

- Check GitHub's **Build calculator app** run. Both the build and **Update website
  deployment branch** jobs should succeed. `pages/deployment.json` records the
  source commit and run URL. Then check the Worker build in Cloudflare.
- To retry publication, rerun the workflow on main. If the publisher says main
  advanced, use the latest main build. If GitHub rejects a pages push, inspect
  repository rules; do not disable protections or force push.
- The publisher calls `build/check_pages.py` to validate required assets,
  source archives, manifest/vendor hashes and Cloudflare file-size limits.
  Its historical filename applies to Workers static assets too.
- Preserve `public/_headers` for cross-origin isolation and Serial/USB
  permissions. Check `crossOriginIsolated === true` on the hosted site and
  that the manifest lists all 23 transfer objects.
- The largest initial asset, webtilp-source.zip, is 25,642,244 bytes, under the
  25 MiB limit. Keep both corresponding-source ZIPs alongside the code. The
  calculator ZIP, WASM and source ZIP URLs must return their actual bytes.
  Missing files are configured to return 404.
- Edit website source and `build/cloudflare/` templates on main. Full build
  outputs stay off main. The calculator transfer manifest is public/package.json,
  separate from any Node package manifest; do not install dependencies there.
- If the site says "The download package is unavailable", Cloudflare is
  serving unbuilt source: `/package-meta.json` returns 404 and `/package.json`
  is the 129-byte Node file instead of the calculator manifest. Set the Worker's
  production branch to `pages` and root directory to `/`, as above. The
  `name` in the generated `wrangler.jsonc` must match the Worker name (`cas`).
- Cloudflare account setup, live DNS/TLS and physical calculator acceptance are
  separate checks. Successful Git publication alone proves none of those steps.

Official references: [Git integration](https://developers.cloudflare.com/workers/ci-cd/builds/git-integration/),
[build settings](https://developers.cloudflare.com/workers/ci-cd/builds/configuration/),
[static assets](https://developers.cloudflare.com/workers/static-assets/),
[custom domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/),
and [headers](https://developers.cloudflare.com/workers/static-assets/headers/).
