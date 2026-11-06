# UI: themes and language

Canonical rules for the UI's colors (four themes, §1–§4) and its two languages, Vietnamese and English (§5–§9). Layout, typography, spacing, radius, elevation and density come from the V2 Stitch design system, [design/stitch/v2/exports/01-character-library/DESIGN.md](../design/stitch/v2/exports/01-character-library/DESIGN.md) (*Atelier Latte & Matcha*, D-039), for the whole app; this document replaces that file's *Colors* section and wins where the two differ. The v1 [design/stitch/DESIGN.md](../design/stitch/DESIGN.md) is archived. Both topics are **frontend-only display preferences**: they are not part of the API, the contracts or job data, and the API, error codes, job data and logs stay in English ([CONTRACTS.md §5.2](CONTRACTS.md#52-errorresponse-every-non-2xx-response) already lets the frontend localize `message` by `code`). Decisions: [D-023](DECISIONS.md) (themes), [D-024](DECISIONS.md) (language). Requirements: FR-U1…FR-U9 in [PRODUCT_SPEC.md](PRODUCT_SPEC.md#5-functional-requirements).

The UI has **two modes (light, dark) with two color themes each**, so four themes in total.

## 1. Color themes

Themes come in two **families**, and each family has one light and one dark member. Switching mode keeps the family, so the app keeps its character and only the lightness changes.

| Family | Light theme | Dark theme |
|---|---|---|
| **Coffee** | `latte`: latte-peach surfaces, roasted-coffee accent, sage as the second accent. *From the owner's first reference image (brown and cream), retuned to the V2 Stitch palette (D-039).* | `caffe`: roasted-brown surfaces, caramel/crema accent, sage foam as the second accent. |
| **Green** | `mint`: white and mint surfaces, periwinkle accent, leaf green as the second accent. *From the owner's second reference image (mint and periwinkle).* | `matcha`: deep tea-green surfaces, matcha-powder accent, rice cream as the second accent. |

All four themes share **mana violet** (`--mana`), the V2 Stitch signal colour for live work (§3 rule 9).

Only the **colors** come from the reference images. Layouts, illustrations, photos and watermarks from the images are not used.

## 2. Tokens

Every color in the UI is a CSS custom property. Each theme sets the full token list on `:root[data-theme="<id>"]`. Components use only these semantic names and never write hex values.

| Token | Role | `latte` | `mint` | `caffe` | `matcha` |
|---|---|---|---|---|---|
| `--canvas` | Page background, viewport floor | `#fff8f6` | `#f4faf6` | `#17100c` | `#0e1410` |
| `--surface` | Panels, cards | `#fffdfc` | `#fdfffd` | `#211814` | `#151d17` |
| `--surface-2` | Inputs, nested groups, table headers | `#fff1ec` | `#e9f4ee` | `#2b201a` | `#1d2820` |
| `--surface-3` | Hover, selected rows, popovers | `#ffe6dd` | `#dcece3` | `#372820` | `#27352a` |
| `--border` | Structural separators (decorative) | `#efdcd5` | `#cde2d6` | `#4a372d` | `#33443a` |
| `--border-control` | Input, select and checkbox outlines (≥ 3:1) | `#8a7a75` | `#5f8270` | `#8f776a` | `#698371` |
| `--text` | Body text, values | `#2e150b` | `#14261d` | `#f7ebe4` | `#e8f1e8` |
| `--text-muted` | Labels, secondary text (≥ 4.5:1) | `#5c4741` | `#44604f` | `#cbb4a8` | `#abbdad` |
| `--primary` | Main actions, focus, active nav, links | `#72564c` | `#4a5ea3` | `#d9a878` | `#a8cf7f` |
| `--primary-hover` | Primary hover | `#4e342e` | `#3a4c8c` | `#e6bc90` | `#badc95` |
| `--on-primary` | Text and icons on `--primary` | `#ffffff` | `#ffffff` | `#1d1410` | `#142010` |
| `--secondary` | Second accent: secondary tags, 2nd chart series, links on hover | `#4f6a50` | `#2f6b40` | `#c5d1b3` | `#dccb9c` |
| `--accent-soft` | Fill only (never text): selected chips, highlights, progress tracks | `#ffe2d9` | `#dcefe3` | `#41302a` | `#2c3d26` |
| `--accent-soft-2` | Fill only: 2nd soft fill (tags, illustrations) | `#e9f2ea` | `#e3e8f8` | `#2f2a3f` | `#2d2a42` |
| `--mana` | Live state only (§3 rule 9): running work, data flowing on canvas edges, the selected node, the generate trigger. Text-capable | `#6b38d5` | `#6433c9` | `#c8adff` | `#c8adff` |
| `--mana-soft` | Fill only: background of running badges and the glow base | `#efe6ff` | `#ece5ff` | `#33284d` | `#2d2748` |
| `--success` | Completed, fresh, ok | `#13704a` | `#1e6b40` | `#86cf9f` | `#7fd3a6` |
| `--warning` | Warnings, stale, low quota | `#7f5200` | `#7a5000` | `#efbd60` | `#e8c06a` |
| `--error` | Errors, failed, insufficient | `#ae1a1a` | `#a8283c` | `#ffa99f` | `#f4968d` |
| `--info` | Neutral notices | `#1d6188` | `#1f5f80` | `#94c8ee` | `#9bc0e4` |
| `--focus-ring` | Keyboard focus outline (2 px) | `#72564c` | `#4a5ea3` | `#d9a878` | `#a8cf7f` |
| `--viewer-bg` | Image and GLB viewer background | `#f6ebe6` | `#e6f0ea` | `#120c09` | `#0b100c` |
| `--viewer-grid` | GLB viewer grid lines | `#d9c6bf` | `#b9d1c3` | `#4a372d` | `#314034` |
| `--shadow` | Elevation shadow color (cards, nodes, modals; §3 rule 6) | `#4e342e24` | `#1e3a2c1f` | `#00000099` | `#00000099` |

Status tints (badge backgrounds) are derived: `color-mix(in srgb, var(--success) 14%, var(--surface))`, and the same for warning, error and info. Do not add separate hex values for them.

**Chart series**, in this order: `--primary`, `--secondary`, `--info`, then `--warning`. Keep a chart to at most 4 series.

**Contrast check (2026-11-06, D-039 palette).** Every text token (`--text`, `--text-muted`, `--primary`, `--secondary`, `--mana`, `--success`, `--warning`, `--error`, `--info`) was measured on each background (`--canvas`, `--surface`, `--surface-2`, `--surface-3`, `--accent-soft`); `--text` and `--mana` also on `--mana-soft`. `--on-primary` was measured on `--primary` and `--primary-hover`. `--border-control` and `--focus-ring` were measured on `--canvas`, `--surface` and `--surface-2`. All reach WCAG AA: 4.5:1 for text and 3:1 for control outlines and the focus ring. The lowest text pair is `--secondary` on `--accent-soft` in `latte`, at 4.88:1. Any change to a token value must be re-checked, and the frontend test in M1 checks this automatically.

## 3. Graphic design rules

1. **60-30-10.** About 60% of the screen is `--canvas`/`--surface`, 30% is `--surface-2`/`--surface-3` and borders, and at most 10% is accent (`--primary`, `--secondary`, soft fills). A screen that looks colorful has too much accent.
2. **One primary action per view.** Only the main action (Generate, Retry) uses a filled `--primary` button. Other buttons are outlined or ghost.
3. **Accent is a signal, not decoration.** `--primary` marks what is interactive or active. Large passive areas (cards, sidebars) never use a saturated fill; they may use `--accent-soft`.
4. **Status color always comes with text or an icon** (for example "● failed", "fresh"). Color alone never carries meaning. This matters most in `matcha`, where primary and success are both green.
5. **Status colors keep their meaning in every theme.** Green means ok, amber means warning, red means error, blue means info. A theme may shift their shade, never their hue family.
6. **Hierarchy by lightness first, then soft elevation.** Each surface level differs from its neighbour by a visible step. Shadows are warm and soft, all derived from `--shadow`: level 1 (cards, canvas nodes) `0 2px 8px -2px`, level 2 (hover, selected node) `0 8px 24px -4px`, level 3 (modals, popovers, a node being dragged) `0 16px 36px -8px`. No other shadow values, and never a shadow as the only cue for state.
7. **Generated content keeps priority.** Image and 3D previews sit on `--viewer-bg`, a quiet neutral that is not pure white or pure black, so the asset's own colors read correctly.
8. **One structure for all themes.** Typography (Plus Jakarta Sans for headings and labels, Be Vietnam Pro for body text, both bundled with the app, never loaded from a CDN), spacing, radius (8 px controls, 16 px cards, 24 px modals) and density follow the V2 Stitch DESIGN.md. A theme changes color only, never layout or size.
9. **Mana means live.** `--mana` and its glow (`0 0 20px 2px` of `--mana` at about 22%) mark only things that are really live or selected: a running job or batch, data available to flow along a canvas edge, the selected node, the generate trigger. Never decoration, never a fake progress state. Animations using it stop under `prefers-reduced-motion` (a static highlight remains).
10. **No demo data.** Stitch exports contain invented numbers (GPU temperature, VRAM, latency, quota, ratings, progress percentages, character art). The UI shows only values from the API; where the API has none, the element is omitted or shows *Unknown* (NFR-3).

## 4. Theme behavior

- **Mode setting** has three values: `light`, `dark` and `system`. `system` (the default) follows `prefers-color-scheme` and updates live when the OS setting changes.
- **Family setting** has two values: `coffee` (default) and `green`.
- The theme in use is `{coffee, green} × {light, dark}` → `latte`, `mint`, `caffe` or `matcha`. It is set as `data-theme` on `<html>`, and CSS `color-scheme` is set to `light` or `dark` so native scrollbars and form controls match.
- **Persistence:** the choice is stored in `localStorage` under `aas.theme` as `{"mode": "...", "family": "..."}`. Every read and write is wrapped in `try/catch`. If storage is unavailable, the defaults apply and the page still works.
- **No flash:** a small inline script in `index.html` sets `data-theme` before the first paint.
- **Switcher:** placed in the top header. It has a three-way mode control (Light / Dark / System) and two family swatches, each showing its accent color with a text label. It is fully keyboard accessible, and each part has an accessible name.
- **Three.js viewer:** reads `--viewer-bg` and `--viewer-grid` from computed style and updates without reloading the model when the theme changes. Its light and material colors are not themed.
- **Motion:** theme changes have no transition animation, or one of at most 150 ms when `prefers-reduced-motion` is not set.

## 5. Language behavior

- **Languages:** `vi` and `en`. English is the source language and the fallback for any missing key.
- **First visit:** if `navigator.languages` contains a `vi*` entry the UI starts in Vietnamese; otherwise it starts in English.
- **Switcher:** in the top header next to the theme switcher, labeled with the language's own name ("Tiếng Việt", "English"), never a flag. It is keyboard accessible.
- **Persistence:** `localStorage` key `aas.locale` (`"vi"` or `"en"`), with every read and write wrapped in `try/catch`. The choice applies before the first paint, like the theme (§4).
- `<html lang>` is always set to the active language, so screen readers pronounce it correctly.
- **Dates and numbers** use `Intl` with the app's locale (`vi-VN` or `en-US`), not the browser default, and `Intl` decides the exact format. For example, the decimal separator is a comma in Vietnamese (`18,5 giờ`) and a point in English (`18.5 h`). Units come from the dictionary (`giờ`/`h`); `GiB` stays the same in both.

## 6. What is translated and what is not

| Translated | Kept exactly as is |
|---|---|
| All UI text: navigation, headings, labels, buttons, help text, empty states, tooltips and `aria-label`s | Brand and product names: AI Asset Studio, Kaggle, NVIDIA T4 |
| Pipeline, category, job status, image role and freshness names | Identifiers: `job_id`, `model_id`, `upload_id`, `artifact_id`, file names |
| Error and warning text, chosen by `code` (§7) | Error codes themselves. They are shown small next to the translated text, for support |
| Units and relative times ("5 phút trước") | Backend log lines (`[MOCK] …`, notebook output) |
| Frontend-generated validation messages | Model `display_name` values from the backend registry |

## 7. Error and warning messages

1. Look up `errors.<CODE>` in the active dictionary and fill its placeholders from `details` (for example `{max_images}`, `{provided}`, `{missing_roles}`).
2. If the key is missing, or a placeholder it needs is not in `details`, show the backend's English `message` instead. **Never** show an empty message or a raw key.
3. Every error code in [CONTRACTS.md §8.2](CONTRACTS.md#82-error-codes) has a Vietnamese entry. A test enforces this.
4. Messages say what happened and what to do next, in plain words. Example, `MODEL_REQUIRED_VIEW_MISSING`: "Hãy thêm ảnh góc {missing_roles} theo yêu cầu."

## 8. Glossary

Use these terms everywhere so the same thing always has the same name. Terms marked *(giữ)* stay in English because Vietnamese users use them that way.

| English | Tiếng Việt |
|---|---|
| Generate studio | Xưởng tạo |
| Generate (button) | Tạo |
| Asset library | Thư viện tài sản |
| Jobs & logs | Tác vụ & nhật ký |
| Kaggle resources | Tài nguyên Kaggle |
| Job | Tác vụ |
| Retry | Thử lại |
| Delete | Xóa |
| Pipeline | Quy trình |
| Text → 2D / Image → 3D / Text → 3D | Văn bản → 2D / Ảnh → 3D / Văn bản → 3D |
| Asset category | Loại tài sản |
| `character` / `skill_effect` / `weapon` / `companion` | Nhân vật / Hiệu ứng kỹ năng / Vũ khí / Thú đồng hành |
| Model | Mô hình |
| Prompt | Prompt *(giữ)* |
| Negative prompt | Prompt loại trừ |
| Upload / Download | Tải lên / Tải xuống |
| Image role | Vai trò ảnh |
| `front` / `side` / `back` / `three_quarter` / `detail` / `style_reference` | Mặt trước / Mặt bên / Mặt sau / Góc ba phần tư / Chi tiết / Tham chiếu phong cách |
| `created` / `uploading` / `queued` / `running` / `downloading` / `completed` / `failed` | Đã tạo / Đang tải lên / Đang chờ / Đang chạy / Đang tải kết quả / Hoàn thành / Thất bại |
| Error / Warning | Lỗi / Cảnh báo |
| Compute profile | Hồ sơ tính toán |
| Accelerator | Bộ tăng tốc |
| Auto (accelerator) | Tự động |
| Quota | Hạn mức |
| Session | Phiên |
| Resource plan | Kế hoạch tài nguyên |
| Estimate / estimated | Ước tính |
| Telemetry | Số liệu giám sát |
| `fresh` / `stale` / `unavailable` / `unsupported` / `not_applicable` | Mới / Cũ / Không có dữ liệu / Không hỗ trợ / Không áp dụng |
| Unknown | Không rõ |
| `ok` / `unknown` / `insufficient` (fit) | Đủ / Không rõ / Không đủ |
| Artifact | Kết quả |
| Preview | Xem trước |
| Light / Dark / System | Sáng / Tối / Theo hệ thống |
| Coffee / Green (theme family) | Cà phê / Xanh lá |

## 9. Writing and layout rules

- **Tone:** short, polite and direct. Address the user neutrally (no "bạn ơi", no slang). Buttons are verbs ("Tạo", "Thử lại", "Tải xuống").
- **Text length:** Vietnamese is often 20–40% longer than English. Layouts must not overflow, clip or wrap badly at 1024 px and 1440 px. Do not shorten a translation to make it fit; fix the layout.
- **Diacritics:** Inter must render Vietnamese with its own glyphs (load the Vietnamese subset of `@fontsource/inter`), not a fallback font. Uppercase labels keep their diacritics ("TRẠNG THÁI"); line height must leave room for stacked marks (ế, ộ, ữ).
- **Sentence case** in both languages, except where a style rule in [DESIGN.md](../design/stitch/DESIGN.md) requires uppercase labels.
- The honesty rules (NFR-3) apply to wording too: estimates say "ước tính", unknown values say "Không rõ", and stale data is never described as live.
- **Model picker time:** each real model (`is_mock: false`) shows its mean time per image after the name, from `runtime.estimated_runtime_seconds` (D-034): `Animagine XL 4.0 (~25 giây/ảnh)` / `(~25 s/image)`. From 90 s on, minutes are shown, rounded to whole minutes: `(~6 phút/ảnh)` / `(~6 min/image)`. The `~` marks an estimate. A tooltip says it was measured on a Kaggle T4 and excludes setup and download. Mock models and a missing value show no time.
