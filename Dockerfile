FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CHRONICLER_STATE_PATH=/chronicler/data/state.json \
    CHRONICLER_LEDGER_PATH=/chronicler/data/ledger.sqlite

WORKDIR /chronicler

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . && \
    useradd --create-home --uid 1000 chronicler && \
    mkdir -p /chronicler/data && chown -R chronicler:chronicler /chronicler/data
USER chronicler

VOLUME /chronicler/data

# The daemon is healthy when the local wiring checks out: Ollama reachable,
# the ledger readable and the target checkout a Git repository.
HEALTHCHECK --interval=60s --timeout=20s --start-period=10s --retries=3 \
    CMD ["chronicler", "--quiet", "doctor"]

ENTRYPOINT ["chronicler"]
CMD ["run"]
