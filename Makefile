# Blindspot: `make` lists every command.
SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help lint lint-backend lint-frontend lint-infra audit-workflows format format-check test test-ci-scripts \
	test-backend test-frontend audit scan-source clean

# Linters run from images pinned by digest, not from third-party GitHub Actions, so the same
# versions run here and in CI. Dependabot raises these (docker ecosystem) in its own PRs.
HADOLINT_IMAGE := hadolint/hadolint:v2.15.1@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d
SHELLCHECK_IMAGE := koalaman/shellcheck:v0.11.0@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d
ACTIONLINT_IMAGE := rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667
TRIVY_IMAGE := aquasec/trivy:0.76.2@sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb
PRETTIER := npx --yes prettier@3.10.1
ZIZMOR := uvx --no-build zizmor@1.33.1
BACKEND := cd backend &&
FRONTEND := cd frontend &&
TRIVY_FLAGS := --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1

# Dockerfiles and shell scripts anywhere in the repository (not dependencies or build output).
DOCKERFILES := $(shell git ls-files '*Dockerfile' '*Dockerfile.*' 2>/dev/null)
SHELL_SCRIPTS := $(shell git ls-files '*.sh' 'docker/s6/*/run' 2>/dev/null)

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

## ---- Checks ---------------------------------------------------------------------
lint: lint-backend lint-frontend lint-infra format-check ## Run every linter and type checker

lint-backend: ## ruff, pyright and bandit (skipped until the backend exists)
	@if [ -f backend/pyproject.toml ]; then \
		$(BACKEND) uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run bandit -c pyproject.toml -r app -q; \
	else echo "No backend yet: skipped."; fi

lint-frontend: ## ESLint, Prettier and vue-tsc (skipped until the web app exists)
	@if [ -f frontend/package.json ]; then \
		$(FRONTEND) npm run lint -- --max-warnings=0 && npm run format:check && npm run typecheck; \
	else echo "No frontend yet: skipped."; fi

lint-infra: ## actionlint, ShellCheck and hadolint (workflows, scripts, Dockerfiles)
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo $(ACTIONLINT_IMAGE) -color
	@if [ -n "$(SHELL_SCRIPTS)" ]; then \
		docker run --rm -v "$(CURDIR):/mnt:ro" $(SHELLCHECK_IMAGE) --external-sources --source-path=SCRIPTDIR $(SHELL_SCRIPTS); \
	fi
	@for file in $(DOCKERFILES); do \
		echo "hadolint $$file"; \
		docker run --rm -i $(HADOLINT_IMAGE) hadolint - < "$$file" || exit 1; \
	done

audit-workflows: ## zizmor: audit the GitHub workflows for security mistakes
	$(ZIZMOR) .github/workflows

format-check: ## Prettier check of docs, workflows and configuration
	$(PRETTIER) --check .

format: ## Auto-format docs and configuration (and the backend and frontend once they exist)
	$(PRETTIER) --write .
	@if [ -f backend/pyproject.toml ]; then $(BACKEND) uv run ruff check --fix . && uv run ruff format .; fi
	@if [ -f frontend/package.json ]; then $(FRONTEND) npm run lint -- --fix && npm run format; fi

test: test-ci-scripts test-backend test-frontend ## Run every test

test-ci-scripts: ## Tests of the scripts in .github/scripts
	./.github/scripts/tests/run-all.sh

test-backend: ## pytest (skipped until the backend exists)
	@if [ -f backend/pyproject.toml ]; then $(BACKEND) uv run pytest; else echo "No backend yet: skipped."; fi

test-frontend: ## Vitest with coverage (skipped until the web app exists)
	@if [ -f frontend/package.json ]; then $(FRONTEND) npm run coverage; else echo "No frontend yet: skipped."; fi

audit: ## Check dependencies for known vulnerabilities (the frontend fails on critical, as CI does)
	@if [ -f backend/pyproject.toml ]; then $(BACKEND) uv run pip-audit; fi
	@if [ -f frontend/package.json ]; then $(FRONTEND) npm audit --audit-level=critical; fi

scan-source: ## Trivy: vulnerable dependencies, leaked secrets and Dockerfile mistakes
	docker run --rm -v blindspot-trivy-cache:/root/.cache/trivy -v "$(CURDIR):/src:ro" -w /src $(TRIVY_IMAGE) fs $(TRIVY_FLAGS) \
		--scanners vuln,secret,misconfig --ignorefile .trivyignore.yaml .

clean: ## Remove local build and test artifacts
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/.coverage backend/coverage.xml \
		frontend/dist frontend/coverage frontend/e2e-results
