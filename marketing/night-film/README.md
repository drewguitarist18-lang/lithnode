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
- `node render.js --phone` renders `phone.html` (`../lithnode-phone-vertical.mp4`): the run as if a phone filmed the monitor at night, in four handheld takes (typing the job, the scout at work, the verdicts, listed and done). The monitor, desk, a snake plant behind it and the lamp-lit wall are ray traced in WebGL around `footage/run.mp4`, then given a phone camera's shake, rolling shutter, focus, sharpening and noise. The sound is only the room, the keys and the clicks, and there's no text, so add the caption and a sound in the app. Its takes and camera moves are the `clips` in the `FOOTAGE` list at the top of `phone.html`.
  - The typing take plays at a person's pace (`typist()`) rather than the capture's 170 words a minute. Each letter shows on the frame of the footage where it first appeared (`shown`), so a new capture needs those frames measured again.
  - While the run dialog is open, its project folder box shows a temp path with the Windows username in it. Each footage's `folder` (when) and `box` (where) cover it with the empty box from `blankAt`; check them again after a new capture, since a taller dialog moves the box.
- `node render.js --phone --jobs` is the same phone shot of a different job (`../lithnode-phone-jobs-vertical.mp4`, `phone.html?job=jobs`): typing "Find remote marketing jobs that pay over 70k", the scout reading LinkedIn and its six finds, the checkers cutting three ("Pays under $70k", "Not remote", "Reviews 2.9★, staff keep quitting"), the Approve click, and the result's three cover letters in Gmail drafts. Its footage comes from `node capture.js jobs`, which describes and runs the "Job hunt" team (the fake Claude acts it out) and opens the result's Details at the end. On a fresh demo app, first add the Research squad as for `--ads`.
  - `node render.js --phone --jobs --photos` writes its TikTok carousel to `../carousel-jobs/` (`1.jpg` to `8.jpg`): the `jobs` set in `PHOTOS`, the same story slide by slide.
    - It's shot in `phone.html`'s second room, `city`, so it doesn't look like the last post. The same desk and monitor sit under a big window at night, with the city's lights out of focus behind them, a light oak desk, a white keyboard and the lamp off to the right.
    - The rows of buildings, their windows and the sky are drawn in the shader (`outside()`), and the room's lamp and lens are in `ROOMS`.
    - Each photo by the window adds up 12 passes so its blur is smooth.
    - For a still by the window, open `phone.html?t=5&room=city`. The video takes stay at the desk.
- `node render.js --phone --photos` writes a TikTok photo carousel to `../carousel/` (`1.jpg` to `7.jpg`, 1080×1920): the same desk as photos, steadier and less grainy than the video, telling the run slide by slide. Each slide's text is set in TikTok Sans with TikTok's white-and-black outline, so post them in photo mode without adding text. The slides, their moments in `run.mp4`, framing and text are the `PHOTOS` list in `phone.html`.
  - The phone's lenses, its processing (glare, tone curve, sharpening, grain) and the TikTok text style are in `phonecam.js`, so other scenes can use the same camera.
- `node render.js --gym` writes the gym carousel to `../carousel-gym/` (`1.jpg` to `6.jpg`). It opens on three photos in a gym at night from `gym.html`:
  - the gym from the end of the dumbbell rack: mirrors, a bench with the 35s beside it, a power rack and a cable crossover against the red end wall, and treadmills;
  - the phone on the floor, its lock screen showing the "claude reset" timer going off;
  - the rack with the 35s back in their spot.

  It then ends on the desk with `phone.html`'s `gym` set (`phone.html?set=gym`). The gym is path traced like the desk and developed by the same phone. Its shots and their text are the `SHOTS` list in `gym.html`; a shot's `racked` flag puts the 35s back on the rack. `PASSES=8` gives a quick look; the default is 96.

## Hero film (the site's 30-second film, in the new look)

- `node capture.js hero` records the redesigned app (needs the demo Lithnode on 8795): `footage/hero-describe`, `hero-run` and `hero-office`.
- `hero.html` composites it: the site's own black hole shader and crab, Geist type, the app in a panel with lifted close-ups, and its own score. `hero.html?t=12.5` shows a still.
- `node render.js --hero` writes `../lithnode-hero.mp4`. For the site, re-encode it to `site/media/lithnode-film.mp4` and take `site/media/film-poster.jpg` from about 2.5 s.
