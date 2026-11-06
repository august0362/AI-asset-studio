# Canonical Stitch reference

The supplied handoff was four ZIP archives in `interface/frontend/`, each containing
`code.html`, `screen.png`, and an identical `DESIGN.md`. No original HANDOFF.md existed.
This index records their organization; source HTML and screenshots are unchanged.

| Supplied archive | Canonical screen |
|---|---|
| stitch_ai_asset_studio.zip | screens/generate-studio/ |
| stitch_ai_asset_studio (1).zip | screens/jobs-logs/ |
| stitch_ai_asset_studio (2).zip | screens/kaggle-resources/ |
| stitch_ai_asset_studio (3).zip | screens/asset-library/ |

`inventory.json` records original archive and extracted file SHA-256 hashes.
One byte-identical `DESIGN.md` replaces the four archived copies.
After application verification, all four original ZIPs were removed. Before removal,
each archive hash and every extracted entry were checked again against this reference.
No unique source file was deleted.
The extracted HTML uses a light theme; the approved Obsidian palette in DESIGN.md
is the implementation default. Source exports contain speculative functionality
and model names; contracts v1.0 take precedence for application behavior.

The React implementation is exclusively `interface/frontend/`. CDN scripts,
theme-switch boilerplate and placeholder metrics from the exports are references
only and are not executed by the application.
