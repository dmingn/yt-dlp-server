# yt-dlp-server

Minimal web UI for downloading videos with yt-dlp.

Paste a URL in the browser; the server downloads it with fixed yt-dlp settings.

## Assumptions

- Intended for trusted LAN use only. **There is no authentication.**
- Anyone who can reach the service can submit arbitrary URLs for download.
- Job status and logs are stored in SQLite (`DATABASE_PATH`, default `jobs.sqlite3`) and survive restarts.
  On startup, `running` jobs are restored to `queued` (or `scheduled` if they were started from a schedule) and their in-progress logs are cleared, then a loop starts queued jobs up to `MAX_RUNNING` about once a second.
  User-cancelled jobs stay `cancelled`.
  Downloaded files on disk remain.

## Quick start (Docker)

```bash
mkdir -p out data
make up
```

Open `http://<host>:8000`.

Downloaded files are written under `./out` on the host (mounted at `/out` in the container), grouped by extractor / channel / playlist.
Change the root with `OUTPUT_DIR`.
The job database is stored under `./data` (`DATABASE_PATH=/data/jobs.sqlite3`).

Compose also starts a [bgutil](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) PO Token provider and sets `POT_BASE_URL=http://pot-provider:4416` so yt-dlp can use the official mweb + GVS PO Token setup.
Unset `POT_BASE_URL` to leave yt-dlp defaults (no pot extractor-args).

Default is 1 concurrent download (`MAX_RUNNING`).
`MAX_JOBS` caps unfinished jobs and how many finished jobs are retained.

## Local development

```bash
uv sync
mkdir -p out data
OUTPUT_DIR=./out DATABASE_PATH=./data/jobs.sqlite3 uv run python -m yt_dlp_server
```

To enable the same PO Token setup locally, run a bgutil provider (for example `docker run --rm -p 4416:4416 brainicism/bgutil-ytdlp-pot-provider:1.3.2`) and set `POT_BASE_URL=http://127.0.0.1:4416`.

```bash
make playwright-install  # once, for UI tests
make check
```

## License

This project is MIT-licensed.
The Docker image also bundles a GPL build of FFmpeg from [yt-dlp/FFmpeg-Builds](https://github.com/yt-dlp/FFmpeg-Builds); that binary is covered by its own license, not by this project's MIT license.
Source for those builds is available from that repository.
