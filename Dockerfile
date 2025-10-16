FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Twelve Data MCP server from PyPI
RUN pip install --no-cache-dir mcp-server-twelve-data

# (Optional) helps some platforms; Render will auto-detect anyway
EXPOSE 8000

# Start the MCP server (HTTP mode). No unsupported flags.
# Keys are read from env vars you set in Render.
CMD bash -lc 'mcp-server-twelve-data -t streamable-http -k "${TWELVEDATA_API_KEY}" -u "${OPENAI_API_KEY:-}"'
