# Secrets and the vault

Passwords are hashed with Argon2id and the hash is sealed too (see [Accounts](accounts.md)); they can never be read back. Everything else that must stay secret (AI
provider keys, credentials for the systems being tested, credentials found during a test, and
evidence marked sensitive) is **sealed** before it reaches the database. Nothing sensitive is
stored in the clear.

## How a value is sealed

- **AES-256-GCM** with a random 96-bit nonce for every value. GCM also detects any change: an
  edited value is refused, never decrypted to something else.
- Each purpose (`auth`, `providers`, `target-credentials`, `discovered-credentials`, `evidence`) has its
  own key, derived from the app secret key with **HKDF-SHA256**. The purpose is also bound into
  the authenticated data, so a value sealed for one purpose cannot be opened as another.
- A sealed value is a text envelope: `v1:<key id>:<nonce>:<ciphertext>`. The key id is a short
  fingerprint of the key that sealed it, which is what makes rotation possible.

In a model, declare the column as `SealedString(Purpose.PROVIDERS)` or
`SealedJSON(Purpose.TARGET_CREDENTIALS)`. Such a column cannot be written in the clear. It also
cannot be searched or sorted by its value, so keep a separate non-secret field (a name, the last
four characters) for that. `mask()` in `app/redact.py` shows a stored secret as its last four
characters.

## The app secret key

The key is at least 32 characters. Give it to the app in one of these ways:

| How                         | When                                                                                          |
| --------------------------- | --------------------------------------------------------------------------------------------- |
| `BLINDSPOT_SECRET_KEY`      | Any environment                                                                               |
| `BLINDSPOT_SECRET_KEY_FILE` | A Docker secret or any file, such as `/run/secrets/blindspot_key`                             |
| Nothing                     | A key is made the first time and kept in `/data/secrets/secret.key`, readable only by the API |

The generated key is convenient, but it sits next to the data it protects, so a backup of `/data`
contains both. **Supply the key yourself and keep a copy apart from your backups.** Without the
key, sealed values cannot be recovered. If it is missing or too short, the app refuses to start.

`make secret-key` prints a new key.

## Rotating the key

1. Make a new key: `make secret-key`.
2. Set `BLINDSPOT_SECRET_KEY` to the new key and `BLINDSPOT_PREVIOUS_SECRET_KEY` to the old one.
3. Run `make rotate-secret-key` (in the container: `python -m app.vault rotate`). Every sealed
   value is opened with the old key and sealed with the new one, in one transaction. If any
   value cannot be opened, nothing changes.
4. Remove `BLINDSPOT_PREVIOUS_SECRET_KEY` and restart.

Running it again is harmless: values already under the current key are skipped. Until step 3 is
done, the app can still read values sealed with the previous key.

## Logs

A log filter hides anything shaped like a secret before a line is written (provider keys,
tokens, private keys, passwords in assignments and URLs, vault envelopes), and any log field named
like a secret. It is the last line of defence: do not put secrets in log calls.

## Tests

Tests prove that nothing planted as a secret is in the database (every table is read), the logs
or what the vault returns, that a changed or misplaced value is refused, and that rotation works
and can run twice.
