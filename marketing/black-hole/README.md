# The black hole on lithnode.com

`render.html` is a ray tracer: every pixel's light ray is bent around the hole with the Schwarzschild equation, so
the lensing, the photon ring and the brighter approaching side come out of the physics. `render.js` (Node +
`puppeteer-core`, using installed Edge) renders it once at 7680x4800 (wide) and 3600x6000 (tall, for phones).

Then scale each down by half with Lanczos and save as WebP (quality 92) into `site/media/black-hole-wide.webp` and
`site/media/black-hole-tall.webp`. The site shows the image; nothing is rendered in visitors' browsers.

Knobs in `render.html`: `pitch` (camera height: higher means a thinner arc under the hole), `under` (how bright the
underside of the disk is), `streak` (disk texture), `glow` (photon ring), and the star threshold in `sky()`.
