FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Install the Twelve Data MCP server from PyPI
RUN pip install --no-cache-dir mcp-server-twelve-data

# Expose Render port (not strictly required, but nice)
EXPOSE ${PORT}

# Start the server in Streamable HTTP mode, bind to 0.0.0.0:$PORT,
# and read your keys from Render env vars.
CMD bash -lc 'mcp-server-twelve-data \
  -t streamable-http \
  -b 0.0.0.0 \
  -p ${PORT} \
  -k "${TWELVEDATA_API_KEY}" \
  -u "${OPENAI_API_KEY:-}"'
