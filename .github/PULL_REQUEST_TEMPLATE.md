<!-- Thanks for the PR. Keep it focused; small PRs land faster. -->

## Summary

<!-- One or two sentences on what this changes. -->

## Why

<!-- The motivation. If this fixes a bug, link the issue. -->

## Notes for reviewers

<!-- Anything non-obvious: a cloud quirk, a payload shape that
     surprised you, a tradeoff between two approaches you weighed. -->

## Checklist

- [ ] `ruff check pyhusqvarna` is clean
- [ ] `mypy --strict pyhusqvarna` is clean
- [ ] `pytest -q` is green
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] If a new endpoint or WebSocket payload was reverse-engineered,
      the raw capture is in `docs/HUSQVARNA_API_NOTES.md`
