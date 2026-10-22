# Contributing to The Chronicler

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/hamanakam1/the-chronicler.git
   cd the-chronicler
   ```

2. Install dependencies:
   ```bash
   python3 -m pip install -e ".[dev]" --break-system-packages
   ```

3. Ensure Ollama is running with a Qwen model:
   ```bash
   ollama run qwen3.8:latest
   ```

4. Run the test suite:
   ```bash
   python3 -m pytest tests/ -v
   ```

5. Run the linters (CI runs both):
   ```bash
   python3 -m ruff check .
   python3 -m mypy
   ```

## Code Style

- `ruff` owns linting (line length 120) and `mypy` owns types. Both must pass.
- Write tests for any new functionality.
- Update the README if you change configuration defaults or add features.

### The ASCII art

The lowrider wordmark lives in `src/chronicler/ascii_art.py` and is generated
by `scripts/build_lowrider_art.py`. To change the art:

```bash
python3 scripts/build_lowrider_art.py     # rewrites LOWRIDER_ART
python3 scripts/refresh_readme_art.py     # syncs the README block
```

The art is deliberately padded with trailing whitespace to keep the wordmark
aligned; `ruff` is configured to leave those files alone.

### The banner and stdout

The banner is written to **stderr** so stdout stays pipeable — `chronicler
doctor | jq` must keep working. If you add a command that prints machine
readable output, keep that contract.

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request using the `.github/pull_request_template.md` template

## License

By contributing to The Chronicler, you agree that your contributions will be licensed under the MIT License.