#!/bin/sh
# Healthy means: the app answers over https through nginx (and so the API is up), and the
# certificate in use has not expired. The certificate is the container's own, so it is not verified.
set -eu
curl --silent --show-error --fail --insecure --max-time 5 --output /dev/null https://127.0.0.1:8443/api/health
openssl x509 -in /run/blindspot/tls/fullchain.pem -noout -checkend 0 > /dev/null
