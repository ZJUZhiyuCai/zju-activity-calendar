# Repository Guidelines

## Project Structure & Module Organization
`main.py` starts the FastAPI server defined in `web.py`. Core backend logic lives in `core/`, HTTP endpoints in `apis/`, scheduled jobs in `jobs/`, and WeChat/browser drivers in `driver/`. The student-facing product lives in the repo-level `frontend/` directory; its build output is copied into `static/calendar/` and served by this backend. Keep long-form product and architecture docs at the repo root, and place backend utilities in `tools/` or `script/`.

## Build, Test, and Development Commands
Install backend dependencies with `pip install -r requirements.txt`, then copy `config.example.yaml` to `config.yaml`. Run the backend locally with `python main.py -config config.yaml`. For the student-facing frontend, work in `../frontend`: `npm install`, `npm run dev`, `npm run lint`, and `npm run build`. Docker development should read runtime settings from `/.env`; use `docker compose -f compose/docker-compose.dev.yaml up -d --force-recreate`.

## Coding Style & Naming Conventions
Follow the existing style before introducing cleanup. Python uses 4-space indentation, snake_case for modules/functions, and grouped feature folders such as `core/notice/` and `apis/`. There is no enforced formatter config in the repo, so keep imports tidy, avoid broad refactors, and match surrounding conventions.

## Testing Guidelines
Backend test coverage is minimal and mostly lives near the code, for example `core/lax/test_template_parser.py`. Run it from that directory with `cd core/lax && python -m unittest test_template_parser.py`. When touching API, scraping, or scheduler code, do a local smoke test by starting `python main.py` and exercising the affected endpoint. Frontend changes should at least pass `npm run lint` and `npm run build` in `../frontend`.

## Security & Configuration Tips
Do not commit real `config.yaml`, `/.env`, tokens, cookies, or data from `data/`. Start from `config.example.yaml` and `/.env.example`, then keep secrets in local-only config. For deployment environments where WeChat blocks datacenter IPs, prefer the compose `singbox` sidecar and a single `PROXY_URL=` entry in `/.env` instead of duplicating proxy settings across files.

当前项目的技术细节写在 tech.md 中
