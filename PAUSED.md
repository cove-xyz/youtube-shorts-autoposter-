# PAUSED — 2026-07-27

All three workflows are **disabled at the GitHub level** (`gh workflow disable`).
The cron lines are still present in the YAML, so this file is the only thing in
the repo that says the schedules are not running. Re-enable with:

```
gh workflow enable "Post YouTube Short"
gh workflow enable "Post Instagram Carousel"
gh workflow enable "Update Analytics & Theme Scores"
```

Nothing was deleted. The channel, its 360 videos, the token, the secrets and the
variant log are all intact. PostPeer's queue was empty at pause time, so nothing
was left scheduled to fire.

## Why

Focus moved to Living Aloha (`cove-xyz/living-aloha`). The numbers behind that
call, measured on 2026-07-27:

- Channel created 2022-03-14. **360 videos, 86,258 views, 90 subscribers.**
- That is ~1 subscriber per 958 views, and 0.25 subs per video.
- Recent run rate ~500 views/day, median 158 views per upload.
- A 10,000-subscriber goal at that conversion needs ~9.6M views in six months,
  against a current pace of roughly 90k. A 100x gap, not a 2x one.

## TWO BUGS FOUND IN THE FINAL RUNS — fix these before resuming

Both were live the whole time and neither was visible without reading CI logs.

### 1. The Instagram carousel workflow has never once succeeded

```
sqlite3.OperationalError: no such table: theme_scores
```

`run_youtube.py carousel-scheduled` reaches `get_weighted_theme()` without ever
calling `init_db()`. Locally the database already exists so it passes; in CI
`data/*.db` is gitignored, so every scheduled run has died at this line since the
workflow was created. Fix: call `init_db()` before dispatching any command.

### 2. The Reel cross-post fires but cannot host its media

```
[8/8] Cross-posting Reel (1/2 today)...
  media_host: could not determine repo (gh unavailable or unauthenticated)
```

`post_youtube.yml` never passes `GH_TOKEN` to the posting step, so `media_host`
cannot authenticate to create the GitHub Release that serves the public video
URL. `post_carousel.yml` does pass it; the Shorts workflow was missed. Fix: add
`GH_TOKEN: ${{ github.token }}` to the step's `env:`.

Consequence worth stating plainly: **no Reel has ever reached Instagram from this
repo.** The step ran, logged its intent, and failed at hosting — and because the
cross-post is deliberately best-effort so it cannot fail a successful YouTube
upload, the run still reported success. Correct design, but it meant a broken
feature looked like a working one for as long as it existed.
