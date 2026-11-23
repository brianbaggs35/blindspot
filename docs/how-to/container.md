# Running Blindspot in a container

Blindspot is one container: nginx (TLS), the API and PostgreSQL 18, supervised by s6. The database has no TCP port and no password; the API talks to it over a unix socket and PostgreSQL checks who is asking with the kernel (peer authentication).

## Start it

```sh
docker compose up -d
```

Then open <https://localhost>. The first start makes a self-signed certificate, so the browser warns once.

| Setting                     | Default | What it does                                                                                                                                   |
| --------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `BLINDSPOT_HTTPS_PORT`      | `443`   | The port https is published on. `http://` on `BLINDSPOT_HTTP_PORT` (`80`) redirects to it                                                      |
| `BLINDSPOT_HOSTNAMES`       | none    | Comma-separated names and addresses the self-signed certificate is valid for (besides `localhost`)                                             |
| `BLINDSPOT_HSTS`            | `0`     | `1` sends `Strict-Transport-Security`. It covers the whole host name and lasts a year, so it is opt-in                                         |
| `BLINDSPOT_SECRET_KEY`      | none    | The key that seals stored credentials (32 characters or more). Empty: one is made on first start in `/data/secrets`. See [Secrets](secrets.md) |
| `BLINDSPOT_SECRET_KEY_FILE` | none    | The same key, read from a file (a Docker secret), instead of the variable                                                                      |

Set them in the shell or in a `.env` file next to `compose.yaml`.

## Certificates

- **Self-signed (default):** made at the first start, valid for a year, made again when it has less than 30 days left. It lives in the `data` volume.
- **Your own:** put `fullchain.pem` and `privkey.pem` in `./certs` and uncomment the `./certs:/certs:ro` volume in `compose.yaml`. They are copied at every start, so restart after renewing.
- An expired certificate makes the container unhealthy.

## What is stored where

| Path    | What                                                                                                |
| ------- | --------------------------------------------------------------------------------------------------- |
| `/data` | The `data` volume: the database, certificates, the generated secret key, evidence, reports, backups |
| `/run`  | A tmpfs: sockets, the copy of the certificate nginx uses, s6's state                                |
| `/tmp`  | A tmpfs                                                                                             |

Everything else in the container is read-only. Back up the `data` volume.

## How it is locked down

- **Read-only file system**, `no-new-privileges`, a process limit, and every capability dropped except `CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETUID`, `SETGID` and `KILL`. `KILL` is there because the root supervisor must be able to stop the API and PostgreSQL, which run as other users. Without it the signal is refused, and the container cannot stop cleanly.
- **Little runs as root.** The entrypoint, s6 and nginx's master process (which opens the logs and reads the key, as nginx always does) are root. The API runs as `blindspot`, PostgreSQL as `postgres`, started with `setpriv`, and nginx's workers, the processes that handle requests, as `nginx`. This is why Trivy's "image runs as root" finding is ignored in `.trivyignore.yaml`, with this reason and an expiry date.
- **Ports above 1024 inside** (8443 and 8080), so binding them needs no capability. Compose publishes them as 443 and 80.
- **Only nginx listens on TCP.** The API listens on `/run/blindspot/api.sock` (readable by nginx only) and PostgreSQL on `/run/postgresql` (readable by the API only). The smoke test in CI fails if anything else listens.
- **TLS 1.3 only**, no session tickets, no server version, and a Content-Security-Policy without inline scripts or `eval`. Styles are allowed by a per-request nonce that nginx puts in the page; inline style _attributes_ are allowed because Vuetify sets them (they cannot run script).

## Building

```sh
docker build --target runtime -t blindspot .
.github/scripts/run-container.sh blindspot blindspot-local 8443   # the hardened flags compose uses
.github/scripts/smoke-test.sh blindspot-local 8443
```

The image is built on Chainguard's Wolfi and upgrades every package at build time, so a rebuild picks up the day's fixes. Wolfi keeps only the newest version of each package, so packages are not version-pinned; the base image is pinned by its digest instead, and Dependabot's Docker updates keep that digest current.

## Restarts and upgrades

Every step of the entrypoint is safe to repeat. The database is created in a side directory and moved into place only when it is complete, so a crash during the first start leaves nothing half-made. The database is migrated at every start, before the API serves anything, and a copy of it is written to `/data/backups` first when the migration will change it (see [the database](database.md)). Migrations are idempotent too.
