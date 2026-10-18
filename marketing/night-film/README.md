# Night film

A 30-second film of the real app and site, cut together over the night sky and the site's black hole.

1. **Capture** (`capture.js`): records real footage into `footage/`. It needs:
   - the demo Lithnode on 8795, with mock engines so runs cost nothing;
   - the site served on 8797: `python -m http.server 8797 -d site`.

   The story is a non-coding job: describe a product hunt, a scout finds products, two checkers cut the weak ones, you approve, an uploader lists the rest. The fake Claude (`tests/mock_claude.py`) acts it out.

   Each clip gets a `.json` log of every pointer move, click and key. The film uses it to draw the cursor and time the click sounds.
   `footage/hole.mp4` is the site's black hole rendered at full 1920×1200, frame by frame, from a copy of `site/black-hole.js`.
2. **Compose** (`film.html`): the canvas compositor and the 120 BPM score.
   - `SCENES` sets which clip plays when.
   - `map` sets how fast it plays. Anything faster than 1.4× shows a "× speed" chip.
   - `cam` sets where the camera looks.
   - Open `film.html?t=12` through any local server for a still.
3. **Render** (`render.js`): serves the repo itself.
   - `node render.js` writes `../lithnode-night.mp4`.
   - `node render.js --stills 3 12 20` writes PNGs to check.

Both scripts use `puppeteer-core` (set `NODE_PATH`) with installed Edge, and ffmpeg (`FFMPEG` or on PATH). MP4s stay out of git.

## Short cuts for TikTok, Reels and Shorts

- `node render.js --vertical` renders the same film at 1080×1920 (`../lithnode-night-vertical.mp4`).
- `node render.js --vertical --hook` renders a 22-second cut that starts on the run (`../lithnode-hook-vertical.mp4`).
- `node render.js --versus` renders `versus.html` (`../lithnode-versus.mp4`), a 14-second before and after: research by hand on top (drawn), the team's real run below, then the end card. It has its own lo-fi score that drops when the run is approved.
- `node render.js --versus --ads` is the same before and after for writing ad scripts (`../lithnode-versus-ads.mp4`). Its footage comes from `node capture.js ads`, which describes and runs the "Ad scripts" team (the fake Claude acts it out). On a fresh demo app, first add the Research squad: `POST /api/flows {"template": "research"}`.
