# Development

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.14 for you; the image and CI use 3.14.10, see [Running the container](container.md#versions)) and Node.js 24 or newer (22 works for most tasks).

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

| Command                               | What it does                                                                                                           |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `make lint`                           | ruff, pyright, bandit, ESLint, Prettier, vue-tsc, and the workflow and script linters                                  |
| `make test`                           | pytest and Vitest with coverage, and the tests of the CI scripts                                                       |
| `make audit`                          | pip-audit and npm audit                                                                                                |
| `make format`                         | Fix formatting everywhere                                                                                              |
| `make up`, `make down`, `make delete` | Build and start the container; stop it keeping the data; delete everything (see [Running the container](container.md)) |

| `make e2e-host` | Playwright against the API and the built web app on your machine, with browser coverage |
| `make e2e` | Playwright against the real image, started the way people run it (needs Docker) |

pytest and Vitest must stay at 100% coverage; the build fails below 95%. See [Continuous integration](ci.md) for what runs on every pull request.

## End-to-end tests

Playwright tests live in `frontend/e2e/` and run in two modes, with the same specs:

- **Host mode** (`make e2e-host`): Playwright starts the API (`uvicorn`) and the web app built by `npm run build:e2e` (`vite preview`, with the source maps inside the files) and drives Chromium. It also collects the web app's **coverage from the browser** and maps it back to `src/`. CI runs three shards, merges their coverage with `e2e/scripts/merge-coverage.mjs`, fails below 80% of lines and warns below 90%.
- **Container mode** (`make e2e`): the same specs against the image from `docker build`, started by `.github/scripts/run-container.sh` (read-only, capabilities dropped), over https with its self-made certificate. The image has no source maps, so this mode checks behaviour, not coverage.

What the specs cover:

- `smoke.spec.ts`: the page opens with the permission warning and no console errors, the API answers on the same address, errors are problem documents without stack traces, and the theme button works and is remembered.
- `layout.spec.ts`: no horizontal scroll at 320, 390, 600, 768, 1024 and 1280 px, and no animation under `prefers-reduced-motion`.
- `a11y.spec.ts`: axe-core (WCAG 2.2 A and AA, and best practice) on every page, in both themes, at all six widths. It fails on any problem not listed in `e2e/axe-baseline.json`. That file is the "previous run": it starts empty, and an entry needs a reason, so a new problem cannot slip in and an old one is removed by deleting its line.

Most specs run **signed in as an administrator**. `e2e/global-setup.ts` creates that account through the API (or signs in when it exists) and saves the session; the API the tests start gets its settings from `e2e/accounts.ts` (a fixed setup code, relaxed throttles, the `BLINDSPOT_DATABASE_URL` you export). Specs that need a signed-out browser use `SIGNED_OUT`; specs that change accounts make their own with `e2e/people.ts` so they never lock the shared one. Passkey specs use a virtual authenticator and run in host mode only. The database must be PostgreSQL: CI starts a Postgres 18 service, and locally export `BLINDSPOT_DATABASE_URL`.

**When you add a page**, add it to `e2e/pages.ts`; the layout and accessibility specs then cover it. On a machine where Playwright's own browser is not installed, point `E2E_CHROMIUM` at a Chromium binary.

Reports (HTML, traces and screenshots of failures, coverage) are uploaded as artifacts on every CI run.

## Settings

The API reads `BLINDSPOT_*` environment variables (see `backend/app/config.py`). Secrets have no defaults and are never logged.
