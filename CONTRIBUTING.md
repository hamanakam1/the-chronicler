# Contributing to The Chronicler

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/hamanakam1/the-chronicler.git
   cd the-chronicler
   ```

2. Install dependencies:
   ```bash
   python3 -m pip install -e . --break-system-packages
   ```

3. Ensure Ollama is running with a Qwen model:
   ```bash
   ollama run qwen3.8:latest
   ```

4. Run the test suite:
   ```bash
   python3 -m pytest tests/ -v
   ```

## Code Style

- Follow the existing Python formatting (black, isort where applicable)
- Keep the CLI banner ASCII art intact — do not modify `src/chronicler/ascii_art.py`
- Write tests for any new functionality
- Update the README if you change configuration defaults or add features

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request using the `.github/pull_request_template.md` template

## License

By contributing to The Chronicler, you agree that your contributions will be licensed under the MIT License.