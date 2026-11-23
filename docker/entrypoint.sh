#!/bin/sh
# Prepares the container and hands over to s6, which keeps nginx, the API and PostgreSQL running.
# It runs as root, and every step is safe to repeat: a restart, or a crash half way through, leaves
# nothing that stops the next start. Services never run as root (see docker/s6/*/run).
set -eu

log() { echo "entrypoint: $*"; }

DATA=/data
PGDATA="$DATA/postgres"
CERTS="$DATA/certs"
TLS=/run/blindspot/tls
HTTPS_PORT="${BLINDSPOT_PUBLIC_HTTPS_PORT:-443}"

case "$HTTPS_PORT" in
  '' | *[!0-9]*) log "BLINDSPOT_PUBLIC_HTTPS_PORT must be a port number, not '$HTTPS_PORT'"; exit 64 ;;
esac

# --- Directories --------------------------------------------------------------------------
umask 077
mkdir -p "$PGDATA" "$CERTS" "$DATA/evidence" "$DATA/reports" "$DATA/backups"
chown postgres:postgres "$PGDATA"
chmod 0700 "$PGDATA"
chown blindspot:blindspot "$DATA/evidence" "$DATA/reports" "$DATA/backups"

# /run is a tmpfs, so these are rebuilt on every start.
mkdir -p /run/postgresql /run/blindspot /run/nginx /run/s6 "$TLS"
chown postgres:pgsock /run/postgresql
chmod 0770 /run/postgresql
chown blindspot:blindspot /run/blindspot
chmod 0750 /run/blindspot
chown nginx:nginx /run/nginx
chmod 0700 /run/nginx
chown nginx:nginx "$TLS"
chmod 0700 "$TLS"

# --- TLS certificate ------------------------------------------------------------------------
# Use the certificate in /certs when there is one (Let's Encrypt, or your own); otherwise make a
# self-signed one that lasts a year and is made again when it has less than 30 days left.
if [ -r /certs/fullchain.pem ] && [ -r /certs/privkey.pem ]; then
  log "using the certificate in /certs"
  cert=/certs/fullchain.pem
  key=/certs/privkey.pem
else
  cert="$CERTS/selfsigned.pem"
  key="$CERTS/selfsigned.key"
  if [ ! -s "$cert" ] || [ ! -s "$key" ] || ! openssl x509 -in "$cert" -noout -checkend 2592000 > /dev/null; then
    log "making a self-signed certificate (browsers will warn; see docs/how-to/container.md)"
    names="DNS:localhost,IP:127.0.0.1,IP:::1"
    if [ -n "${BLINDSPOT_HOSTNAMES:-}" ]; then
      for name in $(echo "$BLINDSPOT_HOSTNAMES" | tr ',' ' '); do
        case "$name" in
          *[!A-Za-z0-9.:-]* | '') log "ignoring '$name' in BLINDSPOT_HOSTNAMES"; continue ;;
        esac
        if echo "$name" | grep -Eq '^[0-9.]+$|:'; then names="$names,IP:$name"; else names="$names,DNS:$name"; fi
      done
    fi
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 365 \
      -subj "/CN=Blindspot" -addext "subjectAltName=$names" -keyout "$key.new" -out "$cert.new" 2> /dev/null
    mv "$key.new" "$key"
    mv "$cert.new" "$cert"
  fi
fi
cp "$cert" "$TLS/fullchain.pem"
cp "$key" "$TLS/privkey.pem"
chown nginx:nginx "$TLS/fullchain.pem" "$TLS/privkey.pem"
chmod 0600 "$TLS/fullchain.pem" "$TLS/privkey.pem"

# --- nginx settings that depend on the environment --------------------------------------------
if [ "$HTTPS_PORT" = 443 ]; then
  # shellcheck disable=SC2016 # $host and $request_uri are nginx's variables, not the shell's
  echo 'return 308 https://$host$request_uri;' > /run/nginx/redirect.conf
else
  echo "return 308 https://\$host:$HTTPS_PORT\$request_uri;" > /run/nginx/redirect.conf
fi
# HSTS covers the whole host name, including other sites on it, so it is off unless asked for.
if [ "${BLINDSPOT_HSTS:-0}" = 1 ]; then
  echo 'add_header Strict-Transport-Security "max-age=31536000" always;' > /run/nginx/hsts.conf
else
  : > /run/nginx/hsts.conf
fi
chown nginx:nginx /run/nginx/redirect.conf /run/nginx/hsts.conf
chmod 0644 /run/nginx/redirect.conf /run/nginx/hsts.conf

# --- PostgreSQL ----------------------------------------------------------------------------
# The cluster is made in a side directory and moved into place when it is complete, so a crash
# half way through leaves nothing that looks finished. It has no TCP port and no passwords: see
# /etc/blindspot/pg_hba.conf.
if [ ! -f "$PGDATA/PG_VERSION" ]; then
  log "creating the database"
  tmp="$DATA/postgres.initializing"
  rm -rf "$tmp"
  mkdir -p "$tmp"
  chown postgres:postgres "$tmp"
  chmod 0700 "$tmp"
  as_postgres() { setpriv --reuid=postgres --regid=postgres --init-groups --no-new-privs -- "$@"; }
  as_postgres initdb --pgdata="$tmp" --username=postgres --auth-local=peer --encoding=UTF8 \
    --locale-provider=builtin --builtin-locale=C.UTF-8 --locale=C.UTF-8 --data-checksums > /dev/null
  # The application's role and database. Single-user mode runs these without a server or a port.
  printf '%s\n%s\n' \
    "CREATE ROLE blindspot LOGIN;" \
    "CREATE DATABASE blindspot OWNER blindspot;" \
    | as_postgres postgres --single -D "$tmp" -c "hba_file=/etc/blindspot/pg_hba.conf" postgres > /dev/null
  if ! rmdir "$PGDATA"; then
    log "$PGDATA has files in it but no database. Move them away and start again."
    exit 1
  fi
  mv "$tmp" "$PGDATA"
fi

# --- Hand over to s6 -------------------------------------------------------------------------
# s6 needs a place to write its supervision state, and the image's file system is read-only.
# Each service's settings are copied to /run, but its run script is linked to the one in the
# image, because /run is mounted noexec.
rm -rf /run/s6/services
mkdir -p /run/s6/services
for dir in /etc/s6/services/*/; do
  name="$(basename "$dir")"
  mkdir "/run/s6/services/$name"
  for file in "$dir"*; do
    if [ "$(basename "$file")" = run ]; then
      ln -s "$file" "/run/s6/services/$name/run"
    else
      cp "$file" "/run/s6/services/$name/"
    fi
  done
done
log "starting"
exec s6-svscan /run/s6/services
