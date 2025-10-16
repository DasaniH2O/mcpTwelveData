# Use official Python runtime
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# (A) Build from source in this repo (what you have now)
RUN pip install --upgrade pip uv
COPY pyproject.toml uv.lock* README.md LICENSE ./   # ok if some files are missing
COPY src ./src
RUN uv pip install . --system

# Expose the port Render will connect to
EXPOSE ${PORT}

# Start the MCP server in Streamable HTTP mode,
# binding to 0.0.0.0 and using Render's $PORT and your env keys.
# (Use shell form so ${PORT} and env vars expand.)
CMD bash -lc 'python -m mcp_server_twelve_data \
  -t streamable-http \
  -b 0.0.0.0 \
  -p ${PORT} \
  -k "${TWELVEDATA_API_KEY}" \
  -u "${OPENAI_API_KEY:-}"'
