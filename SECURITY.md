# Security Policy

## Supported versions

This library is in alpha and the public API may change at any time.
Security fixes will land on the `main` branch and the most recent
released version. Older versions are not supported.

## Threat model

The Husqvarna cloud APIs are protected by an OAuth2 client-credentials
flow. The two surfaces worth thinking about:

- **The App Key + App Secret.** These authenticate your application
  to the cloud. They are *not* per-user; anyone with both can
  enumerate and control every mower your Husqvarna account owns.
  Keep them out of git (the `.gitignore` excludes `.env*` and
  `*.secret`). Don't paste them into issues or logs.
- **The access token.** Valid for 24 hours. Cached in memory by
  `HusqvarnaAuth`; not persisted. A leaked token gives the same
  level of access as the App Secret for its remaining lifetime.

## Reporting a vulnerability

If you think you've found a security issue in `pyhusqvarna`,
**please do not open a public GitHub issue**. Report it privately via
either:

- GitHub's [private security advisory mechanism](https://github.com/magictom74/homeassistant-husqvarna/security/advisories/new) (preferred)
- Email the maintainer (the email address in `pyproject.toml`)

You can expect:

1. An acknowledgement within ~7 days.
2. A short triage assessment with a severity estimate.
3. A fix on a private branch and a coordinated disclosure timeline.

## What counts as a security issue

Examples of things we'd want to know about privately first:

- A way for the library to leak the App Secret or access token
  outside the expected auth/header surface (e.g. into a stack trace,
  log line, or unrelated HTTP request).
- A way to bypass the per-app cloud authorisation - e.g. cross-tenant
  mower access by manipulating the JSON envelope.
- A condition under which the auto-retry on 401 could re-authenticate
  in a tight loop and trigger the `simultaneous.logins` lock on a
  user's account.

Things that are **not** security issues (please open a normal issue):

- The cloud rejecting a request - that's a protocol bug.
- Crash / DoS bugs that only affect the caller's own process.
- The cloud having a 10 000-req/month rate limit - that's a
  Husqvarna business decision, not something this library can fix.
