"""Run the MCP server over stdio against a running Plantasaurus instance.

    PLANTASAURUS_URL=http://localhost:8000 PLANTASAURUS_TOKEN=pts_… uv run python -m app.mcp_server
"""

import os
import sys

from app.mcp_server import Backend, build_server


def main() -> None:
    token = os.environ.get("PLANTASAURUS_TOKEN", "").strip()
    if not token:
        sys.exit("Set PLANTASAURUS_TOKEN to an API token (Settings → API tokens in Plantasaurus)")
    url = os.environ.get("PLANTASAURUS_URL", "http://localhost:8000")
    build_server(Backend.over_http(url, token)).run(show_banner=False)


if __name__ == "__main__":
    main()
