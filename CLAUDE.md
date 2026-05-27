# web-keyword-scanner

Flask web app that crawls websites and finds pages matching keywords.
Real-time results via Server-Sent Events (SSE). Public at https://github.com/Kalas1980/web-keyword-scanner.

## Stack
- Python 3.14 / Flask / BeautifulSoup4 + lxml / requests
- Virtual env: `.venv/` — activate with `source .venv/bin/activate`
- Run dev server: `.venv/bin/python app.py` (port 5001 — macOS AirPlay uses 5000)
- Run tests: `.venv/bin/pytest test_app.py -v`
- Lint: `.venv/bin/ruff check app.py`
- Type check: `.venv/bin/mypy app.py --ignore-missing-imports`
- Push to GitHub: `bash push-to-github.sh` (reads GITHUB_TOKEN from .env)

## Key files
- `app.py` — Flask backend: `/scan` POST, `/stream/<id>` SSE, `/` homepage
- `templates/index.html` — dark UI: crawl/list/both modes, live stats, export CSV
- `test_app.py` — 19 pytest tests covering all routes and core functions
- `.env` — GITHUB_TOKEN (gitignored, never commit)
- `.env.example` — template for new devs
- `Procfile` / `Dockerfile` / `render.yaml` — deploy configs (Railway / Render / Docker)

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish / frontend design → invoke /impeccable (audit, critique, polish, animate, colorize, typeset)
- Visual polish (quick) → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore

## Health Stack

- lint: .venv/bin/ruff check app.py
- typecheck: .venv/bin/mypy app.py --ignore-missing-imports
- test: .venv/bin/pytest test_app.py -v
- security: .venv/bin/bandit -r app.py
- shell: bash -n push-to-github.sh
