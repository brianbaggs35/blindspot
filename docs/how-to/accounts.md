# Accounts, sign-in and the audit trail

There are two roles. An **admin** can read and change everything. A **viewer** can read, and can
only change their own account (sign out, change their own password, end their own sessions).
Every route in the API says which it needs, and a test fails if one does not.

## First-run setup

There are no default credentials. Until the first administrator exists, the API prints a
**setup code** in the container log:

```text
{"message": "No administrator exists yet. Open the app and enter this setup code to create one: BLND-7K2M-QX9P-HT4C", ...}
```

Read it with `docker logs blindspot`, then open the app and give the code with a username and a
password. Setup works once: after the first account exists, the endpoint answers `409`. The code
is made again at each start while no account exists, so an old code never works. Guessing it is
throttled like a failed sign-in.

## Passwords

- Passwords need 12 to 256 characters, at least four different ones, and must not be a very
  common password or contain the username.
- They are hashed with **Argon2id** using the RFC 9106 low-memory profile (64 MiB, 3 passes,
  4 lanes). The hash is then sealed by the vault before it is stored, so a copy of the database
  alone holds nothing that can be used to guess passwords offline. The sealed hashes are
  re-sealed with the rest when the secret key is rotated ([Secrets](secrets.md)). **Losing the
  secret key means losing every password.**
- A hash made with older settings is replaced at the next sign-in.
- Hashing runs in a thread, so it does not hold up other requests.

## Signing in, lockout and throttling

- Every failure answers the same: `401 invalid_credentials`, whether the name is unknown, the
  password is wrong, the account is locked or it is switched off. An unknown name still costs a
  password check, so timing does not give it away.
- Five wrong passwords in a row lock the account for 15 minutes. While it is locked even the
  right password is refused (and says no more than a wrong one). The audit trail records
  `auth.lockout`.
- An address that fails ten times in five minutes gets `429` with `Retry-After`. This also covers
  guessing the setup code and the current password. Both limits can be changed
  (`BLINDSPOT_LOCKOUT_ATTEMPTS`, `BLINDSPOT_LOCKOUT_MINUTES`, `BLINDSPOT_THROTTLE_FAILURES`,
  `BLINDSPOT_THROTTLE_WINDOW_MINUTES`).

## Sessions

- The cookie `blindspot_session` holds 256 random bits and is `HttpOnly`, `Secure` and
  `SameSite=Strict`. Only the token's SHA-256 is stored, so a copy of the database cannot be used
  to sign in. A new token is made at every sign-in.
- A session ends after 60 minutes without a request (`BLINDSPOT_SESSION_IDLE_MINUTES`) or 12
  hours in all (`BLINDSPOT_SESSION_TOTAL_HOURS`), when it is revoked, or when the account is
  switched off or removed.
- `GET /api/auth/sessions` lists your sessions, and `DELETE /api/auth/sessions/{id}` ends one.
  Changing your password, or an administrator resetting it, signs out the other browsers.
- Behind a plain-http development server the cookie would never be sent; set
  `BLINDSPOT_COOKIE_SECURE=false` there, and only there.

## Requests from other sites (CSRF)

A request that changes something and carries the session cookie (or an `Origin`) must show it
came from the app's own pages: `Sec-Fetch-Site` is `same-origin`, and `Origin` matches `Host`.
Anything else gets `403 cross_site_request`. The nginx proxy passes the browser's `Host`
(including a non-standard port) through for this check.

## The audit trail

Every sign-in (and failure), sign-out, setup, password change and account change is added to
`audit_event` with who, what, when, the address and the browser. Rows are only added: removing
an account keeps the name on what it did. Later changes (settings, secrets, scope, agent launches)
add their own events. Administrators read it with `GET /api/audit`, newest first, filtered by
`action`, `outcome`, `actor` and `since`, and paged with `before` (the previous page's
`next_before`).

## API

| Route                            | Who       | What                                           |
| -------------------------------- | --------- | ---------------------------------------------- |
| `GET /api/auth/status`           | anyone    | Is setup needed, and who is signed in          |
| `POST /api/auth/setup`           | anyone    | The first administrator (needs the setup code) |
| `POST /api/auth/login`           | anyone    | Sign in                                        |
| `POST /api/auth/logout`          | signed in | Sign out of this browser                       |
| `GET /api/auth/me`               | signed in | Who you are                                    |
| `POST /api/auth/password`        | signed in | Change your password                           |
| `GET /api/auth/sessions`         | signed in | Your sessions                                  |
| `DELETE /api/auth/sessions/{id}` | signed in | End one of them                                |
| `GET/POST /api/users`            | admin     | List and add accounts                          |
| `PATCH/DELETE /api/users/{id}`   | admin     | Change (name, role, on or off) or remove       |
| `POST /api/users/{id}/password`  | admin     | Set a new password                             |
| `POST /api/users/{id}/sign-out`  | admin     | Sign the account out everywhere                |
| `GET /api/audit`                 | admin     | The audit trail                                |

An administrator cannot change the role or status of, or delete, their own account, so there is
always one administrator who can sign in.
