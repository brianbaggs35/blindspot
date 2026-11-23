# Security policy

## Reporting a weakness in Blindspot

Please report a security problem privately, not in a public issue.

Use GitHub's private reporting: on the repository page, open **Security**, then **Advisories**, then
**Report a vulnerability**. Describe what you found, how to reproduce it and what it could allow.
You will get an answer, and a fix is made before the details are made public. If that option is not
available to you, open an issue that says only that you have a security report, with no details, and
the maintainer will arrange a private way to receive it.

## What counts

Anything that lets a person who should not have access read, change or run something: a way past
sign-in or the viewer role, a way out of a pentest's scope, a way to read stored secrets, injection,
request forgery, a leak in logs or exports, or a weakness in the container.

Reports about the targets you test with Blindspot are not Blindspot's to answer: report those to
the owner of the target.

## Supported versions

Only the latest release is supported. Fixes are not made to older ones.

## How Blindspot protects what it holds

See [secrets](docs/how-to/secrets.md) and [accounts](docs/how-to/accounts.md): credentials are
sealed with AES-256-GCM at rest, sign-in supports passkeys, and every change is in the audit log.

Using Blindspot is covered by the [terms of use](DISCLAIMER.md) and the
[acceptable use](ACCEPTABLE_USE.md) page.
