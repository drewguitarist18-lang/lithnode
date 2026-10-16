# The black hole on lithnode.com

The site now ray traces it live in the browser: `site/black-hole.js` (the gas streams round, inner lanes faster,
and the camera eases toward the cursor; `?d=` changes the camera distance for tuning). What's below is the offline
renderer, still used for the night film's loop and the still pictures shown without WebGL.

`render.html` is a ray tracer: every pixel's light ray is bent around the hole with the Schwarzschild equation, so
the lensing, the photon ring and the brighter approaching side come out of the physics.

- `frames.js wide 1920 1200 0.14 540` and `frames.js tall 1080 1800 0.26 540` (Node + `puppeteer-core`, using
  installed Edge) render 540 frames each at twice the size, scaled down for smooth edges. The disk turns once over
  the 540 frames, so the 18-second loop has no seam.
- Encode with ffmpeg into `site/media/black-hole-{wide,tall}.{webm,mp4}` (VP9 crf 38; H.264 crf 24, faststart);
  frame 0 becomes the poster, `black-hole-{wide,tall}.webp`.

The look is a near edge-on, monochrome disk: a wide band across the frame with the lensed far side arcing over
and under the shadow. The camera sits far back (160) so stars away from the hole aren't smeared into arcs.

Knobs in `render.html`: `pitch` (camera height), `uRoll` (tilt), the disk's outer radius and `profile` (how far the
disk reaches), `under` (how bright the arc under the hole is), `streak` (disk texture), `glow` (photon ring), the
exposure and contrast at the end, and the star threshold in `sky()`.
