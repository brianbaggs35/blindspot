# Development

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.14 for you) and Node.js 24 or newer (22 works for most tasks).

## Run it

```sh
# The API, on http://127.0.0.1:8000 (health check: /api/health)
cd backend
uv sync
uv run uvicorn app.main:create_app --factory --reload

# The web app, on http://localhost:5173 (it proxies /api to the API)
cd frontend
npm ci
npm run dev
```

In development, set `BLINDSPOT_ENVIRONMENT=development` to enable the API's interactive docs at `/api/docs`.

## Check it

From the repository root:

| Command       | What it does                                                                          |
| ------------- | ------------------------------------------------------------------------------------- |
| `make lint`   | ruff, pyright, bandit, ESLint, Prettier, vue-tsc, and the workflow and script linters |
| `make test`   | pytest and Vitest with coverage, and the tests of the CI scripts                      |
| `make audit`  | pip-audit and npm audit                                                               |
| `make format` | Fix formatting everywhere                                                             |

pytest and Vitest must stay at 100% coverage; the build fails below 95%. See [Continuous integration](ci.md) for what runs on every pull request.

## Settings

The API reads `BLINDSPOT_*` environment variables (see `backend/app/config.py`). Secrets have no defaults and are never logged.
