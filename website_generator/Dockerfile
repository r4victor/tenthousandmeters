FROM ghcr.io/astral-sh/uv:python3.13-alpine

WORKDIR /ttm/website_generator
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY links_updater links_updater
COPY themes themes
COPY pelicanconf.py entrypoint.sh ./

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
