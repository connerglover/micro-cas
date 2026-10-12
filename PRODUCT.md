# cas-evo installer

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Implementation choice under the user's standing instruction to work autonomously:
static HTML, CSS and JavaScript, with the EVO transport from WebTILP. No account,
application server or upload of calculator contents is needed. The user requested
Cloudflare Worker hosting connected to GitHub on their existing connerglover.com
domain. Main contains source; successful builds publish the generated pages
branch for Cloudflare. The proposed hostname is cas.connerglover.com; local use
remains available. See docs/HOSTING.md and docs/STATUS.md for deployment status.

## Users

TI-84 EVO owners installing cas-evo, beginning with Conner. The current package
has 21 compiled library packs and two Python launchers, and replaces a v1 install
of 236 libraries. Selecting their destinations manually is difficult, and
sending all files to RAM produces a memory error on the user's calculator.

## Product Purpose

Connect a calculator in the browser and install the complete, verified cas-evo
package with one explicit installation action and visible progress: compiled
libraries in archive, two source launchers in RAM.

## Operating Context

USB data cable, a compatible desktop browser, calculator powered on. The user
explicitly requested WebTILP from adriweb/tilibs and cited CalcPlex's direct
browser transfer experience. Browser permission still requires a user gesture.

## Capabilities and Constraints

- Preserve all v1 features: compiled companions in archive, launchers in RAM.
- Validate package integrity before transfer; report interruption and retry.
- Do not remove unrelated calculator content or change calculator firmware.
- Physical EVO transfer and execution have not been verified by this agent.
- Repository stays private. The user authorized publishing the built installer
  and attaching a subdomain in Cloudflare. Publish only the website output,
  including the calculator download and required corresponding-source archives.
- Accessibility: semantic controls, visible focus, status announcements,
  responsive layout and reduced-motion support (implementation requirements).

## Brand Commitments

Name: cas-evo. Clear, direct language. This is an installation utility; CalcPlex
is a functional reference, not a request to copy its identity.

## Evidence on Hand

docs/STATUS.md records the verified calculator package, GitHub build and memory
checks. docs/INSTALL.md describes current transfer and launch steps. The new
web installer must distinguish completed browser/protocol tests from physical
calculator validation. No customer, usage or reliability claims are supplied.
