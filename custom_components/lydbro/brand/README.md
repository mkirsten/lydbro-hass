# Brand assets

Icons for the Lydbro Home Assistant integration, served directly from
this `brand/` directory.

## How this works

Since Home Assistant 2026.3.0, custom integrations ship their own brand
images: HA looks for a `brand/` folder inside the integration directory
and uses it in the UI, taking priority over the
`brands.home-assistant.io` CDN. No `home-assistant/brands` PR is needed
(that repo no longer accepts custom-integration icons — see the
[brands proxy API announcement](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api)).

HACS's default-store validation likewise accepts an in-repo `brand/`
directory with at least `icon.png`.

## Files

| File | Size | Notes |
|---|---|---|
| `icon.svg`    | source   | Transparent background, monochrome glyph (`#e0e0e0`) |
| `icon.png`    | 256×256  | RGBA, transparent background |
| `icon@2x.png` | 512×512  | RGBA, transparent background |
| `logo.png`    | 256×256  | Same as icon for now (no wordmark yet) |
| `logo@2x.png` | 512×512  | Same as icon@2x for now |

## Regenerating the PNGs

If the SVG changes, rerun from this directory:

```bash
rsvg-convert -w 256 -h 256 -a icon.svg > icon.png
rsvg-convert -w 512 -h 512 -a icon.svg > icon@2x.png
rsvg-convert -w 256 -h 256 -a icon.svg > logo.png
rsvg-convert -w 512 -h 512 -a icon.svg > logo@2x.png
```
