FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /chronicler

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir . && \
    useradd --create-home --uid 1000 chronicler && \
    mkdir -p /chronicler/data && chown chronicler /chronicler/data
USER chronicler

VOLUME /chronicler/data

ENTRYPOINT ["chronicler"]
CMD ["run"]
