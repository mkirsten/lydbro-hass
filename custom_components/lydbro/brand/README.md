# Brand assets

Icons for the Lydbro Home Assistant integration, ready to submit to
[`home-assistant/brands`](https://github.com/home-assistant/brands).

## Why

HA looks up every custom integration's icon at
`https://brands.home-assistant.io/<domain>/icon.png`. Until the Lydbro
assets land in the `home-assistant/brands` repo and the CDN refreshes,
the HA UI shows *"icon not available"* on the integration card. There
is no local override — it has to go through a PR.

## Files

| File | Size | Notes |
|---|---|---|
| `icon.svg`    | source   | Transparent background, monochrome glyph (`#e0e0e0`) |
| `icon.png`    | 256×256  | RGBA, transparent background |
| `icon@2x.png` | 512×512  | RGBA, transparent background |
| `logo.png`    | 256×256  | Same as icon for now (no wordmark yet) |
| `logo@2x.png` | 512×512  | Same as icon@2x for now |

All four PNGs are rasterized from `icon.svg` with `rsvg-convert -a`
(keeps aspect, transparent bg).

## Submitting to home-assistant/brands

One-time setup:

```bash
cd ~/Development
git clone git@github.com:mkirsten/brands.git   # your fork
cd brands
git remote add upstream https://github.com/home-assistant/brands.git
git fetch upstream
```

Each time you update the assets:

```bash
cd ~/Development/brands
git checkout main && git pull upstream main && git push origin main
git checkout -b add-lydbro-icons

mkdir -p custom_integrations/lydbro
cp ~/Development/lydbro-hass/brand/icon.png      custom_integrations/lydbro/
cp ~/Development/lydbro-hass/brand/icon@2x.png   custom_integrations/lydbro/
cp ~/Development/lydbro-hass/brand/logo.png      custom_integrations/lydbro/
cp ~/Development/lydbro-hass/brand/logo@2x.png   custom_integrations/lydbro/

git add custom_integrations/lydbro/
git commit -m "Add Lydbro custom integration icons"
git push -u origin add-lydbro-icons
gh pr create --repo home-assistant/brands \
  --title "Add Lydbro custom integration icons" \
  --body "Icons for the [lydbro-hass](https://github.com/mkirsten/lydbro-hass) custom integration. Transparent background, 256/512 px, monochrome glyph."
```

After the PR merges upstream, the CDN refreshes within minutes and the
HA UI picks up the icon on the next page load — no HA restart needed.

## Regenerating the PNGs

If the SVG changes, rerun from the repo root:

```bash
cd brand
rsvg-convert -w 256 -h 256 -a icon.svg > icon.png
rsvg-convert -w 512 -h 512 -a icon.svg > icon@2x.png
rsvg-convert -w 256 -h 256 -a icon.svg > logo.png
rsvg-convert -w 512 -h 512 -a icon.svg > logo@2x.png
```
