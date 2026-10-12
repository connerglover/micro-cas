---
name: cas-evo installer
description: A clear file workspace for installing cas-evo on a TI-84 EVO.
colors:
  ground: "#edf0f4"
  paper: "#fff"
  ink: "#202a3b"
  muted: "#586579"
  line: "#d4dbe5"
  blue: "#2144ad"
  blue-dark: "#183383"
  blue-pale: "#e8eefb"
  green: "#21644d"
  green-pale: "#e4f1e9"
  error: "#903e29"
  error-pale: "#fff0e9"
  control-line: "#a4b0c2"
  file-ready: "#e5e9f0"
  divider: "#cbd3df"
typography:
  display:
    fontFamily: '"Public Sans",sans-serif'
    fontSize: "44px"
    fontWeight: 600
    lineHeight: 1.12
    letterSpacing: "-0.04em"
  headline:
    fontFamily: '"Public Sans",sans-serif'
    fontSize: "23px"
    fontWeight: 550
    lineHeight: 1.55
    letterSpacing: "-0.035em"
  title:
    fontFamily: '"Public Sans",sans-serif'
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.55
    letterSpacing: "-0.025em"
  body:
    fontFamily: '"Public Sans",sans-serif'
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  supporting:
    fontFamily: '"Public Sans",sans-serif'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: '"Public Sans",sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.55
  button:
    fontFamily: '"Public Sans",sans-serif'
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.55
  filename:
    fontFamily: "ui-monospace,SFMono-Regular,Consolas,monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  file-cell: "1px"
  field: "4px"
  control: "6px"
  package: "12px"
  circle: "50%"
spacing:
  small-gap: "12px"
  mobile-inset: "20px"
  package-inset: "26px"
  compact-gutter: "28px"
  stack-gap: "30px"
  compact-column-gap: "36px"
  desktop-gutter: "40px"
  column-gap: "68px"
components:
  button-primary:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.paper}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "13px 19px"
  button-primary-hover:
    backgroundColor: "{colors.blue-dark}"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    padding: "9px 0"
  input-search:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.field}"
    padding: "8px 10px"
  navigation:
    textColor: "{colors.muted}"
  chip-destination:
    backgroundColor: "{colors.blue-pale}"
    textColor: "{colors.blue}"
    rounded: "{rounded.field}"
    padding: "4px 9px"
  card-package:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.package}"
  stage-current:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.paper}"
    rounded: "{rounded.circle}"
    height: "29px"
    width: "29px"
  transfer-map:
    textColor: "{colors.ink}"
    padding: "23px 26px 19px"
  manifest:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
---

# Design System: cas-evo installer

## Overview

**Creative North Star: "The File Workspace"**

The File Workspace gives the installer the clarity of a desktop file manager: a white working surface on cool silver, direct Public Sans labels, restrained ink-blue selection, and literal representations of package files. Its character is calm, compact and inspectable. Filename and diagnostic text use monospace; the surrounding interface uses proportional type.

State carries the visual emphasis. Solid blue identifies the next action and current work; green identifies a specific verified or completed condition. Rules and tonal changes divide information without shadows. This record describes the implemented web interface, with the durable accessibility and direct-language commitments in PRODUCT.md.

This is an extracted record of website/index.html, website/styles.css and website/app.js, not an approved comp. The session used autonomous, code-led implementation; it establishes no lasting build-path preference. The surface composition and direction remain in .impeccable/surfaces/website-index-html.md. docs/DESIGN.md documents the calculator engine and is separate from this UI system.

**Key Characteristics:**

- A light file workspace with crisp rules and restrained state color.
- Public Sans interface text; monospace filenames and local diagnostics.
- One advancing primary action beside an inspectable package.
- Literal file progress with a filename, count and textual state.
- Responsive stacking, visible focus and reduced-motion support.

## Colors

Cool neutrals establish the work surface; ink-blue action and sage verification provide functional emphasis. The frontmatter preserves the implemented CSS values. The first twelve color tokens come from website/styles.css :root; the remaining three name repeated literal colors in that stylesheet.

### Primary

- **Ink blue** (`blue`): main action, active stage, sending file, links, caret and focus outline.
- **Deep ink blue** (`blue-dark`): primary-button hover.
- **Pale ink blue** (`blue-pale`): the noninteractive compiled-package tag.

### Neutral

- **Cool silver** (`ground`): page background and scrollbar track.
- **White paper** (`paper`): package surface, fields, table header and diagnostic area; also text on the primary action.
- **Dark ink** (`ink`): headings, body text and secondary actions.
- **Slate text** (`muted`): supporting copy, labels and inactive connection text.
- **Workspace rule** (`line`): package borders and internal separators.
- **Control rule** (`control-line`): input and secondary-button strokes; scrollbar thumb.
- **Pending silver** (`file-ready`): unsent file cells and the progress track.
- **Section rule** (`divider`): help, diagnostics and footer boundaries.

### Semantic states

- **Verification green** (`green`) and **pale sage** (`green-pale`): integrity confirmation, completed stage, verified files and post-install guidance. A package-integrity confirmation does not imply a successful device transfer.
- **Attention rust** (`error`) and **pale rust** (`error-pale`): textual notices requiring attention. File failures also have a literal rust cell state, retained in the component snippet.

**The State Evidence Rule.** Color accompanies a named state and a count or message; it never supplies the only indication of progress or completion.

Selection colors, disabled controls and intermediate file-state colors are local component treatments in the sidecar, not a second brand palette. The sidecar's generated tonal ramps are preview metadata only; the application does not use those ramps.

## Typography

Public Sans is self-hosted from website/fonts/public-sans.ttf with weights 100–900 and font-display: swap. The fallback is sans-serif. The filename and diagnostic stack is ui-monospace, SFMono-Regular, Consolas, monospace. The scale is a set of role sizes, not a declared modular ratio.

- **Display:** the frontmatter display role serves the installer heading. At widths up to 1000px its size becomes 36px; up to 700px its width is limited to 14ch. Balanced wrapping and tight tracking hold the two-line introduction together.
- **Headline:** the help heading uses the headline role, with a 24px mobile override.
- **Title:** the package heading uses the title role. Stage headings use 15px at weight 600; the package-description lead uses 17px at weight 600.
- **Body:** the body role establishes the default. The introduction uses 16px/1.7, becoming 14px on mobile, with a 39ch maximum measure.
- **Supporting:** stage copy uses this role with a 36ch measure, expanding to 40ch on mobile. Help copy uses the same 13px size with line-height 1.7 and a 42ch measure; expanded answers allow 64ch.
- **Label:** utility copy, table content, notices about the action, and package facts retain a 12px floor. Fact values and progress headings use weight 550; the package tag uses weight 600.
- **Filename:** filenames and diagnostics use the mono role. Numeric readouts, code and table cells use tabular numerals.

**The Filename Rule.** Reserve monospace for filenames and diagnostics; keep the operating instructions and interface hierarchy in Public Sans.

## Layout

The header, main content and footer share a 1248px maximum border-box width and centered margins. Desktop side padding is 40px. The installer uses minmax(0,1fr) and minmax(0,1.19fr) columns with a 68px gap; help repeats that proportion. The left action sequence precedes the package in source order. These are the current installer surface's measurements, not a mandatory composition for every future page.

| Condition | Implemented behavior |
| --- | --- |
| At least 1400px | Main top padding grows from 30px to 48px; workspace gap becomes 86px; setup top padding becomes 25px. |
| Up to 1000px | Side gutters become 28px; workspace and help gaps become 36px; the second column becomes 1.15fr; display becomes 36px. Package facts use two columns with the final fact spanning both. |
| Up to 700px | A single column puts the action before the manifest; gutters become 20px; workspace gap is 30px. The main button fills its row. Help navigation is hidden while the ZIP link remains. Package facts return to three compact columns. Help gap becomes 28px; footer stacks. |
| Reduced motion | Smooth scrolling becomes automatic and all transitions and animations are removed. |

Package sections generally share 26px side insets, reduced to 20px on mobile. The file map uses 34 columns and 4px gaps, changing to 28 columns and 3px gaps at 1000px and below. Each package file has one cell. The map has an 86px minimum height, becoming 90px on mobile. The manifest scroll area is capped at 240px with sticky table headings; local diagnostics are capped at 250px.

The named spacing entries in frontmatter are extracted recurring measurements, not existing CSS custom properties or a fabricated universal scale. Region-specific vertical spacing remains in website/styles.css.

## Elevation & Depth

The interface uses no box shadows. White paper against the cool silver page, one-pixel rules, and a light connection strip establish depth. The package clips its inner sections to the outer rounded boundary. Sticky table headings keep the white surface behind labels; the keyboard skip link uses a higher stacking level only when focused. No decorative lighting or raster imagery is part of the shipped surface.

**The Surface Rule.** Separate working regions with tone and rules; retain the flat material language of the installed interface.

## Shapes

The package is the broad, softly rounded container. Buttons and notices use the control radius; fields and the compiled tag use the field radius. File cells are nearly square with only the file-cell radius. Stage numbers and the connection dot are circles; the progress bar is square-ended and only 3px high. Manifest rows are separated by fine horizontal rules and have no individual card silhouette.

The primary and secondary actions have minimum heights of 52px and 40px respectively. The primary action has a 256px minimum width above mobile; this minimum is removed when it fills the mobile row. Focus is a 3px blue outline with a 4px offset on buttons, links, inputs, summaries and focusable scroll regions.

## Components

### Actions

The solid primary button pairs a direct label with an inline SVG arrow. Hover deepens its blue, active press uses a darker local fill, and disabled states use muted silver with a subdued arrow. Its background transition is 0.16s ease-out. Secondary controls are transparent, outlined and compact; hover adds a cool fill. Disconnect is an underlined text button. Their functional labels follow website/app.js controls(): connection, installation, retry, busy or reload-required states.

### Navigation and package tag

Header navigation is a plain horizontal group of muted links. Hover turns them blue and underlines them; visible focus uses the shared outline. The compiled-package tag is a static pale-blue label, with no selected state or destination choice.

### Package and manifest

The white package pane groups its heading, description, facts, transfer area, connection strip and manifest with shared edges and rules. The native details/summary manifest is closed by default. Its labeled search field filters filenames without changing the package. The table presents filename, size, required location and state; an explicit empty result appears when nothing matches. Search, summary and scroll region remain keyboard accessible.

### Stage rail

Three numbered stages provide a real sequence: connect, install, then open CASEVO. Current uses solid blue; completed uses pale sage with green text. A fine vertical rule connects the numbers. The active item has aria-current="step"; the visual markers are not a separate navigation control.

### File map and connection strip

The map has one cell for each transfer file the package manifest lists: for packs-v1, 22 files, the 20 compiled packs going to archive and the two tiny source launchers CASEVO and CVTEST going to RAM. There is no destination toggle. Pending, sending, sent, verified and failed cells use distinct fills. A 0.18s ease-out transition applies only to background and border color; it does not simulate progress. Cells are aria-hidden because the textual status, numeric count, progress element and manifest communicate the state accessibly.

website/app.js advances file states from installer progress events. Sent and final verified states are distinct; final completion follows the file-location check. The connection strip separately reports the connected model and available archive space when provided. Package verification, transfer completion and calculator execution remain separate truths.

### Notices, help and diagnostics

Attention appears in a rust-tinted alert with wrapping text. Successful installation reveals green launch guidance. Help and connection details use native disclosure controls. The local diagnostic log uses wrapping mono text in a bounded scroll region, with a copy action and explicit copy fallback text.

### Recorded evidence and conditional states

.impeccable/review/finish-review.md records a ship disposition with no material fixes and reviews desktop.png, mobile.png and user-1280.png in the same folder. Those captures show the settled package-ready state, verified download integrity, zero transferred files and no calculator connection. This documenter uses that review as the visual evidence record; it does not claim a new browser or hardware run.

Loading, connecting, connected, transferring, stopped, completed, retry, lost connection, unsupported browser, integrity failure, search-empty and copy-result states are conditional implementations inspected in website/index.html and website/app.js. They are not all observed screenshot states. Physical USB transfer and calculator execution remain unverified by this record. No approved or decision comp exists, and no shipping raster asset needs provenance.

## Do's and Don'ts

### Do:

- Do pair state color with textual status and numeric progress.
- Do use Public Sans for the interface and monospace for filenames and diagnostics.
- Do preserve visible keyboard focus, semantic controls and reduced-motion behavior.
- Do keep required archive and RAM destinations visible and automatic.
- Do treat package verification, file-location verification and calculator execution as separate conditions.

### Don't:

- Don't turn the static package tag into a destination toggle.
- Don't use the pending or success file colors as decorative progress.
- Don't claim a connected or installed device from the package-ready screenshot.
- Don't replace the flat workspace hierarchy with shadows or individually boxed file rows.
- Don't treat this session's code-led implementation as a standing workflow preference.
