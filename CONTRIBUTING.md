# Contributing to homeassistant-husqvarna

Thanks for taking an interest. This project covers the Husqvarna
Connect cloud APIs - today the Automower Connect API end-to-end.
Architecture is deliberately built so further product families can
slot in alongside the mower module without a rewrite.

## What kind of contributions are welcome

- Bug fixes verified against a real mower (or any Husqvarna Connect
  device once we add more product families).
- New cloud endpoints with a matching captured payload in
  `docs/HUSQVARNA_API_NOTES.md` and a test against the captured
  shape.
- Additional product-family modules (`pyhusqvarna.api.<family>` +
  `pyhusqvarna.models.<family>`) for any other Husqvarna cloud
  product that shares the Group OAuth.
- Improvements to the WebSocket reconnect handling - this is the
  area with the most cloud-specific quirks (1001/1006 close codes,
  the `simultaneous.logins` lock, the 24-hour token rotation).

## Local development

```bash
git clone git@github.com:magictom74/homeassistant-husqvarna.git
cd homeassistant-husqvarna

# Install in editable mode with dev extras
pip install -e ".[dev]"

# Run the three local checks - all must pass before opening a PR
ruff check pyhusqvarna
mypy --strict pyhusqvarna
pytest -q
```

CI runs the same three checks on Python 3.10, 3.11, and 3.12.

## Coding standards

- **Type hints everywhere.** The library passes `mypy --strict`.
- **Frozen dataclasses** for domain models.
- **Defensive parsers.** The cloud occasionally adds fields or sends
  partial sub-trees over WebSocket. `from_raw` classmethods must
  tolerate missing keys and unknown enum values (fall back to
  `UNKNOWN`, never raise).
- **No polling.** Initial REST snapshot plus the WebSocket push -
  that's the architecture. Polling triggers the
  `simultaneous.logins` lock on the cloud.
- **Tests for new code.** REST changes need a respx-mocked test;
  new event shapes need a payload-based test in
  `tests/test_models.py`.

## Reverse-engineering a new endpoint

Before adding an endpoint that isn't in `docs/HUSQVARNA_API_NOTES.md`:

1. Capture a real request/response pair against the cloud.
2. Add the pair to `docs/HUSQVARNA_API_NOTES.md`.
3. Add a respx-based test in `tests/` with the captured payload.
4. Then implement the client method.

## Pull request checklist

- [ ] `ruff check pyhusqvarna` is clean
- [ ] `mypy --strict pyhusqvarna` is clean
- [ ] `pytest -q` is green
- [ ] New behaviour is covered by a test
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] If a new endpoint or WebSocket payload was reverse-engineered,
      the raw capture is in `docs/HUSQVARNA_API_NOTES.md`

## License

By contributing you agree that your contribution will be licensed
under the project's [MIT license](LICENSE).
