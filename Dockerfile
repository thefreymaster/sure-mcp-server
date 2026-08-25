FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
RUN curl -LsSf https://astral.sh/uv/0.9.29/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Copy dependency files first for better caching
COPY requirements.txt pyproject.toml ./

# Install dependencies
RUN uv pip install --system -r requirements.txt

# Copy application code
COPY src/ ./src/

# Install the package in editable mode
RUN uv pip install --system -e .

# SURE_API_URL and SURE_API_KEY are required and must be supplied at
# runtime (docker run -e / compose environment) - intentionally not
# declared here so no placeholder value ends up baked into the image.
ENV SURE_TIMEOUT="30"
ENV SURE_VERIFY_SSL="true"

# MCP HTTP transport settings (Streamable HTTP - the standard for hosting
# this server on a network, e.g. Unraid, rather than spawning it over stdio)
ENV MCP_TRANSPORT="streamable-http"
ENV MCP_HOST="0.0.0.0"
ENV MCP_PORT="8000"
ENV MCP_PATH="/mcp"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,socket; socket.create_connection(('127.0.0.1', int(os.environ['MCP_PORT'])), timeout=3).close()" || exit 1

# Run the MCP server over HTTP (see MCP_TRANSPORT above)
CMD ["python", "-m", "sure_mcp_server.server"]
