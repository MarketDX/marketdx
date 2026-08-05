# MarketDX MCP server — hosted (Streamable HTTP) for mcp.marketdx.lab.ai.
# Per-request auth: each caller sends `Authorization: Bearer <their-key>` (or, later, an OAuth
# token) — the server never holds a shared MarketDX key. DEEPSEEK_API_KEY (composite tools only)
# is the one runtime secret; inject it via Cloud Run --set-secrets.
#
# Install DEPENDENCIES from PyPI (all wheels — no build) and run server.py directly; we don't build
# the package (a flat single-module app needs no packaging just to run).
FROM python:3.12-slim

WORKDIR /app
# mcp pinned <2: 2.0.0 moved `mcp.server.fastmcp` and breaks the import (server.py:19).
RUN pip install --no-cache-dir \
      "mcp>=1.8.0,<2" "marketdx>=0.14.0" "openai>=1.0.0" "uvicorn>=0.30.0"
COPY server.py policy.md favicon.ico gics_taxonomy.json ./

ENV MCP_TRANSPORT=http \
    PORT=8080
EXPOSE 8080
CMD ["python", "server.py"]
