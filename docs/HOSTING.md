# Cloudflare Pages hosting

Target: **cas.connerglover.com**, project **cas-evo**, production branch **v1**.
The short hostname is easy to type; the site itself retains the cas-evo name.
See HANDOVER.md for the actual deployment status. A configured workflow alone
does not mean the site is live.

Use a Pages **Direct Upload** project. GitHub Actions already builds and tests
the calculator, then creates the self-contained website. Pages serves that
exact artifact; it does not need another calculator build or repository access.
The GitHub repository stays private.

## Initial deployment

Authenticate with Wrangler in a terminal (Node 22 or later):

```powershell
npx --yes wrangler@4.149.0 login --scopes account:read user:read pages:write zone:read
npx --yes wrangler@4.149.0 whoami
npx --yes wrangler@4.149.0 pages project list
```

Use the Cloudflare account that owns connerglover.com. Inspect existing projects
and DNS records before making changes. If cas-evo does not already exist, create
it with `npx --yes wrangler@4.149.0 pages project create cas-evo --production-branch v1`.
Set `CLOUDFLARE_ACCOUNT_ID` in the process environment if multiple accounts are
available. Do not commit credentials or Wrangler authentication state.

Download **cas-evo-web-installer** from a successful **Build calculator app**
run, extracting to `dist/pages`. Its layout must include `dist/pages/website`.
Only deploy that inner folder, never the repository root or the whole `dist`:

```powershell
python build/check_pages.py dist/pages/website
npx --yes wrangler@4.149.0 pages deploy dist/pages/website --project-name cas-evo --branch v1
```

In Cloudflare, open **Workers & Pages → cas-evo → Custom domains → Set up a
custom domain** and enter **cas.connerglover.com**. Confirm the proposed CNAME
only after checking it does not replace an unrelated record. Cloudflare can
create the record in the existing zone. Associate the domain with the Pages
project first; a DNS record alone is insufficient. Leave the apex domain and
other subdomains unchanged. Wait for the custom domain and certificate to become
active, then verify HTTPS at the target hostname.

## Automatic updates

Create an account-scoped Cloudflare API token for **Account → Cloudflare Pages →
Edit**, limited to the account hosting this project. No DNS permission is needed
for routine deployments. In the private GitHub repository's **Settings → Secrets
and variables → Actions**, configure:

| Type | Name | Value |
| --- | --- | --- |
| Repository secret | `CLOUDFLARE_API_TOKEN` | The scoped deployment token |
| Repository variable | `CLOUDFLARE_ACCOUNT_ID` | The Cloudflare account ID |

Add the token first and the account variable last. Do not paste the token into
chat, code, commit messages or command arguments. The CLI alternative is
`gh secret set CLOUDFLARE_API_TOKEN`, which prompts privately for its value.

The existing build workflow publishes only successful `v1` push/manual builds.
Pull requests and other branches never publish production. With no account
variable, deployment is skipped and the calculator/site downloads still build.
With an account variable but no token, the deployment job fails with an explicit
configuration error. Once both are configured, push to `v1` or rerun the workflow
on `v1` to publish. Its `deploy` job downloads only the current run's tested
installer artifact and uploads its `website/` directory using pinned Wrangler.

## Checks and maintenance

- Run `python build/check_pages.py <website-directory>` before publishing.
  It checks required assets/licenses, browser headers, manifest/vendor checksums,
  unexpected root files, and Pages file-count/per-file limits.
- Keep `_headers` in the upload root. All responses need
  `Cross-Origin-Opener-Policy: same-origin` and
  `Cross-Origin-Embedder-Policy: require-corp` for the WASM transport. Preserve
  `Permissions-Policy: serial=(self), usb=(self)` too.
- On the live site, confirm `crossOriginIsolated === true` in desktop Chrome/Edge,
  package count 238, the complete file list, and successful WASM initialization.
  Verify the calculator ZIP, source ZIPs and WASM URLs return their expected
  bytes/MIME types, not the fallback HTML page. A device chooser requires a user
  gesture; actual USB transfer and calculator execution remain hardware checks.
- The initial artifact contains 28 files. Its largest asset, `webtilp-source.zip`,
  is 25,642,244 bytes, below Pages' 25 MiB (26,214,400-byte) limit. Preserve this
  corresponding-source download for the distributed WebTILP code. Future vendor
  upgrades must pass the size check rather than silently removing the archive.
- Failed builds leave the previous Pages deployment intact. Use Pages' deployment
  history to roll back if needed. Direct Upload projects cannot switch to native
  Git integration; GitHub Actions supplies automatic deployments here.

Official references: [Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/),
[CI deployment and scoped token](https://developers.cloudflare.com/pages/how-to/use-direct-upload-with-continuous-integration/),
[custom domains](https://developers.cloudflare.com/pages/configuration/custom-domains/),
[headers](https://developers.cloudflare.com/pages/configuration/headers/), and
[limits](https://developers.cloudflare.com/pages/platform/limits/).
