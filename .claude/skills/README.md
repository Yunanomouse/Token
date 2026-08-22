# Taste Skill — installed design skills

Source: [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) (MIT, © 2026 Leonxlnx).
Vendored from the `taste-skill-main` release archive. Full licence text: `LICENSE-taste-skill`.

Folders are named by each skill's `name:` frontmatter (the install name), so Claude Code
picks them up as project skills automatically.

## Implementation skills (output code)

| Skill | Use it when |
|---|---|
| `design-taste-frontend` | **Default.** v2. Landing pages, portfolios, redesigns. Reads the brief, sets three dials, avoids templated output. |
| `design-taste-frontend-v1` | Only if you need v2's predecessor's exact behaviour. |
| `gpt-taste` | Stricter GPT/Codex variant — higher layout variance, heavier GSAP direction. |
| `redesign-existing-projects` | Audit-first upgrade of an existing UI, without breaking it. |
| `high-end-visual-design` | Direction already chosen: calm, premium, soft contrast, spring motion. |
| `minimalist-ui` | Direction already chosen: editorial, Notion/Linear, restrained palette. |
| `industrial-brutalist-ui` | Direction already chosen: Swiss type, hard contrast, experimental layout. |
| `image-to-code` | Image-first pipeline — generate references, analyse them, then build to match. |
| `stitch-design-taste` | Google Stitch rules; can export a `DESIGN.md`. |
| `full-output-enforcement` | The model keeps truncating or leaving `// ...` placeholders. |

## Image-generation skills (output images only, no code)

| Skill | Produces |
|---|---|
| `imagegen-frontend-web` | Website comps — one horizontal image per section. |
| `imagegen-frontend-mobile` | Mobile screens and flows in phone mockups. |
| `brandkit` | Brand boards — logo directions, palette, type, applications. |

## The three dials

`design-taste-frontend` and its variants are tuned by three 1–10 dials. Baseline is **8 / 6 / 4**;
override them conversationally rather than by editing the skill file.

- **DESIGN_VARIANCE** — 1 symmetric and centred, 10 asymmetric and experimental.
- **MOTION_INTENSITY** — 1 static, 10 cinematic scroll and physics.
- **VISUAL_DENSITY** — 1 airy gallery, 10 packed dashboard.

## Note on scope

`design-taste-frontend` states its own boundary: landing pages, portfolios and redesigns —
not dashboards, data tables, or multi-step product UI. For those, reach for a real design
system via the skill's brief-to-system map instead.
