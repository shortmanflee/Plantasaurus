# Development image: Python 3.12 + uv (same versions as the production Dockerfile)
# with Node 22 added by a devcontainer feature.
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /usr/local/bin/

# sqlite3 CLI for poking at the dev database. The base image's Yarn apt repo
# has an expired signing key that breaks apt-get update, and we use npm anyway.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Docker creates the parent of a nested volume mount (/home/vscode/.cache/uv)
# as root. Create it in the image, owned by the dev user, so tools like
# code-server can write to ~/.cache.
RUN mkdir -p /home/vscode/.cache/uv \
    && chown -R vscode:vscode /home/vscode/.cache
