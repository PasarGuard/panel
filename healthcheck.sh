#!/bin/bash

PORT=${UVICORN_PORT:-8000}
CERTFILE=${UVICORN_SSL_CERTFILE}
KEYFILE=${UVICORN_SSL_KEYFILE}

# Determine protocol based on SSL files
if [ -f "$CERTFILE" ] && [ -f "$KEYFILE" ]; then
    # SSL files exist - use HTTPS
    PROTOCOL="https"
    CURL_FLAGS="-sf --insecure"
else
    # No SSL files - use HTTP
    PROTOCOL="http"
    CURL_FLAGS="-sf"
fi

# Run health check
curl $CURL_FLAGS "${PROTOCOL}://127.0.0.1:${PORT}/health" || exit 1