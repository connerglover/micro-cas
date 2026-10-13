# cas-evo website deployment

This generated `pages` branch contains the tested web installer in `public/` and
its Cloudflare Worker configuration. Application and website source live on
`main`. Make changes there: each successful main build updates this branch.
`deployment.json` identifies the source commit and successful build.

In Cloudflare Workers & Pages, create a Worker by connecting this GitHub repository:

| Setting | Value |
| --- | --- |
| Worker name | `cas` |
| Production branch | `pages` |
| Root directory | Repository root (`/`) |
| Build command | Leave empty |
| Deploy command | `npx --yes wrangler@4.149.0 deploy` |
| Builds for other branches | Disabled |

For an existing Worker, connect the repository under Settings > Builds and use
the same settings. The generated assets are already built; no Python or npm
build is needed here. Cloudflare handles its deployment credential through the
GitHub integration. The repository can stay private.

After deployment, use Settings > Domains & Routes > Add > Custom Domain to attach
`cas.connerglover.com`. Cloudflare manages the DNS record and HTTPS certificate.
Only `public/` is served. Keep its `_headers`, downloads, fonts, licenses and
corresponding-source archives intact. The branch name `pages` is used with a
Cloudflare Worker; enabling GitHub Pages is not required.

Physical calculator transfer/execution remains a separate acceptance check.
