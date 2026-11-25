# Changelog

All notable changes to Blindspot are written here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

How a release is made, and what to update with it, is in [Contributing](docs/how-to/contributing.md#releases).

## [Unreleased]

## [0.0.1] - 2026-11-25

The first version: the foundation of the platform. It has the container, sign-in and the secrets vault, the AI provider settings, the methodology engine with the OWASP WSTG checklist, and pentests with their authorization gate, scope and checklist. The agents and the security tools come in the next versions, so this version cannot run a test yet.

### Added

- **Single container** with nginx and TLS (a self-signed certificate on the first start), the API and PostgreSQL 18 on a unix socket with no password, supervised by s6. The image is built from a digest-pinned Wolfi base, runs read-only with its capabilities dropped, and shuts down cleanly. The database is migrated when the container starts, after a `pg_dump` copy when the structure will change.
- **Continuous integration**: formatting, actionlint, ShellCheck and hadolint (from images pinned by digest), ruff, pyright, bandit, ESLint and vue-tsc, pytest and Vitest with coverage, Playwright against the API and against the real image (three shards each, with merged browser coverage), Trivy for dependencies, secrets and the image, CodeQL, zizmor, SonarQube with a quality gate and a report of what it found, and a ticket-key check on every branch, commit and pull request title. Dependabot raises weekly updates.
- **Release workflow** that builds, scans and smoke tests the image for amd64 and arm64, publishes a multi-platform image to the GitHub Container Registry with signed build provenance and SBOMs, and attaches the SBOMs to the release.
- **Backend** on FastAPI with SQLAlchemy 2 (async), psycopg 3 and Alembic, with structured logs that redact secrets, one error shape for every failure, and a health route that reports the release.
- **Secrets vault**: AES-256-GCM sealing with a key per purpose derived by HKDF-SHA256, sealed column types, an app secret key that can be rotated, and log redaction.
- **Accounts**: first-run setup with a setup code, Argon2id passwords (the hash is sealed too), sessions, administrator and viewer roles, sign-in lockout, CSRF checks, passkey (WebAuthn) sign-in with user verification and clone detection, and an audit log.
- **Web app** on Vue 3, Vuetify and TypeScript: the Situation Room design in a dark and a light theme, a collapsible menu built from the router, a command palette, a switch for visual effects, shared loading, empty and error states, and a layout that works on a phone. Dialogs have accessible names, and axe checks every page in both themes.
- **Pages** for first-run setup, sign-in, passkeys and the account, for users and the audit log (administrators), and for the terms of use.
- **Terms of use** that everyone accepts before using the app, versioned by a fingerprint of the words, with `DISCLAIMER.md`, `ACCEPTABLE_USE.md` and `SECURITY.md`.
- **AI providers**: Anthropic, OpenAI and Ollama (local and cloud) behind one interface on Pydantic AI, keys sealed in the vault, an address guard that refuses private and metadata addresses for hosted providers, test connection, fetch models, a price catalog with overrides, a usage ledger with token classes and cost, monthly budgets with a hard stop, a default model for each agent role, and a settings page for all of it.
- **Methodology engine**: methodologies as data (YAML packs), the OWASP WSTG checklist (13 categories, 133 tests) imported and mapped to tools, playbooks for each test, and a Methodologies page.
- **Pentests**: create, edit, clone, archive, trash, restore, export and import; a scope compiler that refuses ranges and addresses it must never allow; an authorization gate and status lifecycle (permission statement kept with who agreed, when and from where); a per-pentest checklist with status, notes, evidence links and custom tests; authorization warnings in the forms and a launch dialog that lists what will run.
- **Documentation**: the platform plan, research notes, a guide for each part, the logo, and the Apache License 2.0.

[Unreleased]: https://github.com/brianbaggs35/blindspot/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/brianbaggs35/blindspot/releases/tag/v0.0.1
