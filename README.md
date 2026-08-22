# yt-dlp-server

Minimal web UI for downloading videos with yt-dlp.

Paste a URL in the browser; the server downloads it with fixed yt-dlp settings.

## Assumptions

- Intended for trusted LAN use only. **There is no authentication.**
- Anyone who can reach the service can submit arbitrary URLs for download.
- Job status and logs are stored in SQLite (`DATABASE_PATH`, default `jobs.sqlite3`) and survive restarts.
  On startup, `running` jobs are restored to `queued` (or `scheduled` if they were started from a schedule) and their in-progress logs are cleared, then a loop about once a second starts due scheduled jobs even beyond `MAX_RUNNING`, and queued jobs up to `MAX_RUNNING`.
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

Default is 1 concurrent download (`MAX_RUNNING`).
`MAX_JOBS` caps unfinished jobs and how many finished jobs are retained.

## Local development

```bash
uv sync
mkdir -p out data
OUTPUT_DIR=./out DATABASE_PATH=./data/jobs.sqlite3 uv run python -m yt_dlp_server
```

```bash
make playwright-install  # once, for UI tests
make check
```

## License

This project is MIT-licensed.
The Docker image also bundles a GPL build of FFmpeg from [yt-dlp/FFmpeg-Builds](https://github.com/yt-dlp/FFmpeg-Builds); that binary is covered by its own license, not by this project's MIT license.
Source for those builds is available from that repository.
