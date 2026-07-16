# MarketDX MCP server — hosted (Streamable HTTP) for mcp.marketdx.lab.ai.
# Per-request auth: each caller sends `Authorization: Bearer <their-key>` (or, later, an OAuth
# token) — the server never holds a shared MarketDX key. DEEPSEEK_API_KEY (composite tools only)
# is the one runtime secret; inject it via Cloud Run --set-secrets.
FROM python:3.12-slim

WORKDIR /app
# deps first (layer cache), then the app + its policy.md resource
COPY pyproject.toml README.md ./
COPY server.py policy.md ./
RUN pip install --no-cache-dir .

ENV MCP_TRANSPORT=http \
    PORT=8080
EXPOSE 8080
CMD ["marketdx-mcp"]
