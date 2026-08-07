# yt-dlp-server

Minimal web UI for downloading videos with yt-dlp.

Paste a URL in the browser; the server downloads it with fixed yt-dlp settings.

## Assumptions

- Intended for trusted LAN use only. **There is no authentication.**
- Anyone who can reach the service can submit arbitrary URLs for download.
- Job status and logs live in memory and are lost on restart. Downloaded files on disk remain.

## Quick start (Docker)

```bash
mkdir -p out
docker compose up --build
```

Open `http://<host>:8000`.

Downloaded files are written under `./out` on the host (mounted at `/out` in the container), grouped by extractor / channel / playlist. Change the root with `OUTPUT_DIR`.

Default is 1 worker (`N_WORKERS`). `MAX_JOBS` caps unfinished jobs and how many finished jobs are kept in memory.

## Local development

```bash
uv sync
mkdir -p out
OUTPUT_DIR=./out uv run python -m yt_dlp_server
```

```bash
make check
```

## License

This project is MIT-licensed. The Docker image also bundles a GPL build of FFmpeg from [yt-dlp/FFmpeg-Builds](https://github.com/yt-dlp/FFmpeg-Builds); that binary is covered by its own license, not by this project's MIT license. Source for those builds is available from that repository.
