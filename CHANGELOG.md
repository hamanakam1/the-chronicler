# Changelog

All notable changes to The Chronicler are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Failures are no longer silently skipped.** The ledger reader returned the
  *newest* N failures while the daemon advances a watermark to the newest row
  it has seen. Every failure older than the batch was therefore hidden behind
  the watermark and never processed. The reader now returns the oldest
  unprocessed failures first, so a backlog drains in order and nothing is
  lost.
- **A single bad audit no longer blocks the pipeline.** One malformed local
  LLM response raised out of `run_cycle` before the watermark was saved, so
  the daemon re-read the same poison entry on every poll, forever, and never
  reached the healthy audits behind it. Per-audit failures are now isolated
  and reported in `CycleReport.failed_audits`; the rest of the batch still
  lands.
- **Committing identical content is no longer an error.** `git commit` exits
  non-zero with an empty message when there is nothing staged, which aborted
  the cycle. The committer now checks the index first and returns a receipt
  with status `unchanged`.
- `run_forever` no longer returns the `None` value of `run_forever` as an
  exit code; the CLI now exits `0` after the daemon stops.
- `git rev-parse HEAD` on an empty repository no longer raises; the receipt
  simply carries `sha=None`.

### Added

- **`--quiet` / `-q` flag.** Suppresses the ASCII banner. Accepted both
  before and after the subcommand (`chronicler --quiet doctor` and
  `chronicler doctor --quiet`).
- **The banner now goes to stderr.** stdout is pure JSON, so
  `chronicler doctor | jq` works. Previously the banner was interleaved with
  the payload and broke JSON parsing.
- **`--log-level` flag.** Configures daemon verbosity (`debug`, `info`,
  `warning`, `error`, `critical`). The daemon log is written to stderr with
  timestamps; before this, logging was never configured and cycle activity
  was invisible.
- **Cycle-level logging.** Each cycle reports how many failures it ingested,
  how many heuristics it learned, how many files it wrote, how many commits
  it made, and how many audits failed.
- **`ruff` and `mypy` configuration**, plus a `lint` job in CI.
- **New tests** covering ledger ordering, committer failure modes and
  per-audit resilience.
- **`scripts/build_lowrider_art.py`** regenerates the lowrider ASCII art and
  **`scripts/refresh_readme_art.py`** syncs it into the README.
- Project metadata in `pyproject.toml`: keywords, classifiers and URLs.
- Documentation for the CLI, the full configuration surface, and Docker
  Compose.

### Changed

- The ASCII art is now a hand-composed chop-top LA lowrider with round wire
  wheels, chrome trim and a staggered cruise line.
- The README no longer repeats the "Core Autonomous Superpowers" section.
- Removed dead imports and a `make_audit` fixture that was shadowed by the
  identically named fixture in `conftest.py`.

## [0.1.0]

- Initial release: EdgeRecord ledger watcher, local Ollama heuristic
  extraction, rule hardening, lore synthesis and zero-intervention Git
  commits, with the `run`, `watch` and `doctor` CLI commands.
