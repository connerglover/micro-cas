# Cloudflare Worker deployed from Forgejo

Use **cas.connerglover.com**, Worker **cas**, deployment branch **pages**.
The main repository is on Forgejo (https://git.connerglover.com/conner/micro-cas),
which push-mirrors every branch and tag to the GitHub repository. Since
2026-11-14 the release workflow (`.forgejo/workflows/build.yml`) runs on the home
Forgejo runner and deploys the Worker itself with Wrangler; the Cloudflare
dashboard no longer builds from GitHub (Settings → Builds is disconnected).

Secrets on the Forgejo repository (or the `conner` user):

| Secret | Use |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | Wrangler deploy of the `cas` Worker ("Edit Cloudflare Workers" token) |
| `CLOUDFLARE_ACCOUNT_ID` | the Cloudflare account that owns the Worker |
| `GH_RELEASE_TOKEN` | GitHub fine-grained token (Contents: write) so the Release is also published on the mirror |

## Branches

- `main`: calculator and website source, tests, build tooling and documentation.
  The complete v1 history is merged here. Make future changes here or in feature
  branches merged into main.
- `pages`: generated deployment files only, with an independent history.
  `public/` contains the tested installer, calculator download, vendor code and
  license sources. The root contains the Worker config and deployment provenance.
- `v1`: retained for history; it no longer drives production publication.

## Releases

The **Build calculator app** workflow runs only for a pushed tag that starts
with `v` (for example `v1.0.0`), for a GitHub Release published in the UI, and
by hand (**Run workflow**). Ordinary pushes and pull requests do not run it.
To release, set `VERSION` in `build/manifest.py` (and the About text in
`src/menu.py`, which a test keeps equal), commit on main, then tag and push:

```text
git tag -a v1.0.2 -m "MicroCAS 1.0.2"
git push origin v1.0.2
```

A tag run builds and tests everything, then:

- **Attach the calculator ZIP**: creates the Release for the tag on Forgejo and on
  GitHub (`tools/publish-release.sh`) if it does not exist yet (or uses the one created in the UI) and uploads
  `dist/microcas-calculator.zip` as `microcas-<tag>.zip` (`--clobber` replaces a
  previous upload). Only this job and the publish job have contents-write
  permission, from GitHub's built-in token.
- **Update website deployment branch**: updates pages with the exact installer
  artifact from that run, then deploys pages to the Worker with
  `npx --yes wrangler@4.149.0 deploy`.

Creating the release in the GitHub UI with a new tag also works: the
`release: published` event builds and attaches the ZIP. When a tag push and its
Release both start a run, the runs for one tag queue (a concurrency group per
tag). A Release run that finds `microcas-<tag>.zip` already attached skips the
build; a tag-push run that comes second builds again and replaces the ZIP
(`--clobber`), which is harmless. A Release published for a tag that does not
start with `v` builds nothing. A Release created by the workflow's own token
starts no further run. A manual
run on a branch only builds and tests (artifacts on the run page); run it on a
tag to release.

A failed build leaves the previous website and Release assets intact. The
publisher only publishes while the tag still names the built commit, and never
replaces a newer release on pages with an older one (`deployment.json` records
`source_ref`). Updates preserve history and never force push. Do not edit or
merge the generated pages branch into main.

## Earlier setup (before 2026-11-14, kept for reference)

The Worker used to build from GitHub through the Cloudflare dashboard:

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

- Check GitHub's **Build calculator app** run for the tag. The build,
  **Attach the calculator ZIP** and **Update website deployment branch** jobs
  should succeed, and the Release should list `microcas-<tag>.zip`
  (releases before v1.0.2 list `cas-evo-<tag>.zip`).
  `pages/deployment.json` records the source commit, tag and run URL. Then check
  the Worker build in Cloudflare.
- To retry, rerun the tag's workflow run (or **Run workflow** on the tag). If the
  publisher says the tag moved or pages holds a newer release, publish from the
  newest tag instead. If GitHub rejects a pages push, inspect repository rules;
  do not disable protections or force push.
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
