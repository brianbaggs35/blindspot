# Terms of use

Blindspot sends real attacks. Before anybody can use it, they read and accept the terms of use.
The text is in [`DISCLAIMER.md`](../../DISCLAIMER.md); the other legal files are
[`ACCEPTABLE_USE.md`](../../ACCEPTABLE_USE.md) and [`SECURITY.md`](../../SECURITY.md). None of
this is legal advice. Have a lawyer read it before you rely on it.

## What a person sees

After signing in (and after first-run setup), every account lands on the **Terms of use** page
until it has accepted the current version. Nothing else in the app opens: any address is turned
back to the terms and remembered, and after "Accept and continue" the person goes where they were
heading. The page shows the full text, the version, a warning, a checkbox ("I have read these
terms and I accept them") and a sign-out button. Viewers accept too; accepting is something a
person does for their own account.

## How the version works

- The words are data in `backend/app/terms/text.py`. The **version is a fingerprint of the
  words** (the first 12 hex characters of a SHA-256), so changing any word changes the version and
  everybody is asked again. Nothing about the text can change without that.
- The accepted version and time are kept on the account (`app_user.terms_version` and
  `terms_accepted_at`) and a `terms.accept` event with the version goes to the
  [audit log](accounts.md#the-audit-trail).
- If the words change while somebody is reading, accepting the old version is refused with
  `409 terms_changed` and the page shows the new text.

## Changing the text

1. Edit the sections in `backend/app/terms/text.py`.
2. Run `make terms` to write `DISCLAIMER.md` again. A test fails when the file and the code
   differ, and says to run it.
3. The wording is the maintainer's to approve. Have it reviewed by a lawyer.

## What is enforced on the server

The page is a convenience; the API holds the line for the actions that matter:

- Confirming permission to test (`POST /api/pentests/{id}/attest`) and starting or resuming a
  pentest (`POST /api/pentests/{id}/status` to `running`) are refused with
  `403 terms_not_accepted` until the signed-in account has accepted the current terms.
- `GET /api/terms` (anyone signed in) returns `title`, `version`, `accepted`, `accepted_at` and
  the `sections`. `POST /api/terms/accept` with `{"version": ...}` records the acceptance.
- `GET /api/auth/me`, the sign-in answers and the users list carry `terms_accepted`.

## Warnings elsewhere

The authorization step, the scope and the launch check are described in
[Pentests](pentests.md#the-authorization-gate). Warnings in the places that arrive later (agents,
tool settings, the chatbot and report export) are added with those features.
