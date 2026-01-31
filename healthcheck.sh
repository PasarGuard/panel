#!/bin/bash

# Health check script that adapts to different binding scenarios:
# 1. Unix socket (UDS)
# 2. Reverse proxy (Caddy) - health checks through localhost
# 3. Direct HTTP binding
# 4. Direct HTTPS binding

PORT=${UVICORN_PORT:-8000}
CERTFILE=${UVICORN_SSL_CERTFILE}
KEYFILE=${UVICORN_SSL_KEYFILE}
UDS=${UVICORN_UDS}
DEBUG=${DEBUG:-false}

# Decode percent-encoded strings (for http+unix://%2Fpath.sock)
url_decode() {
    local encoded=$1
    printf '%b' "${encoded//%/\\x}"
}

# Normalize UDS values (supports unix://, http+unix://, file://, and abstract sockets)
UDS_IS_ABSTRACT=false
UDS_PATH=""

normalize_uds_path() {
    local raw=$1
    local path=$raw

    UDS_IS_ABSTRACT=false
    UDS_PATH=""

    # Strip surrounding quotes (common in .env files)
    if [[ "$path" == \"*\" && "$path" == *\" ]]; then
        path="${path#\"}"
        path="${path%\"}"
    elif [[ "$path" == \'*\' && "$path" == *\' ]]; then
        path="${path#\'}"
        path="${path%\'}"
    fi

    # Abstract socket prefixes
    case "$path" in
        abstract://*) UDS_IS_ABSTRACT=true; path="${path#abstract://}" ;;
        abstract:*) UDS_IS_ABSTRACT=true; path="${path#abstract:}" ;;
        unix-abstract://*) UDS_IS_ABSTRACT=true; path="${path#unix-abstract://}" ;;
        unix-abstract:*) UDS_IS_ABSTRACT=true; path="${path#unix-abstract:}" ;;
    esac

    # Strip common schemes for filesystem sockets or http+unix URLs
    case "$path" in
        unix://*) path="${path#unix://}" ;;
        unix:/*) path="${path#unix:}" ;;
        unix:*) path="${path#unix:}" ;;
        http+unix://*) path="${path#http+unix://}" ;;
        http+unix:/*) path="${path#http+unix:}" ;;
        https+unix://*) path="${path#https+unix://}" ;;
        https+unix:/*) path="${path#https+unix:}" ;;
        file://*) path="${path#file://}" ;;
        file:/*) path="${path#file:}" ;;
    esac

    # Leading @ indicates an abstract socket name
    if [[ "$path" == @* ]]; then
        UDS_IS_ABSTRACT=true
        path="${path#@}"
    fi

    # Decode percent-encoded paths (e.g., %2F)
    if [[ "$path" == *%* ]]; then
        path="$(url_decode "$path")"
    fi

    # Collapse leading double slashes for filesystem paths
    if [ "$UDS_IS_ABSTRACT" = false ] && [[ "$path" == //* ]]; then
        path="/${path#//}"
    fi

    UDS_PATH="$path"
}

# Function to check health via HTTP/HTTPS
check_http_health() {
    local protocol=$1
    local host=$2
    local port=$3
    local curl_flags="-sf"

    # Add --insecure for HTTPS self-signed certs
    if [ "$protocol" = "https" ]; then
        curl_flags="$curl_flags --insecure"
    fi

    curl $curl_flags "${protocol}://${host}:${port}/health" 2>/dev/null
    return $?
}

# Function to check health via Unix socket
check_uds_health() {
    local socket_path=$1

    normalize_uds_path "$socket_path"

    if [ -z "$UDS_PATH" ]; then
        return 1
    fi

    if [ "$UDS_IS_ABSTRACT" = true ]; then
        if curl -sf --abstract-unix-socket "$UDS_PATH" "http://localhost/health" 2>/dev/null; then
            return 0
        fi
        curl -sf --abstract-unix-socket "@$UDS_PATH" "http://localhost/health" 2>/dev/null
        return $?
    fi

    if [ ! -S "$UDS_PATH" ]; then
        return 1
    fi

    # Use curl with unix socket
    curl -sf --unix-socket "$UDS_PATH" "http://localhost/health" 2>/dev/null
    return $?
}

# Main health check logic
main() {
    # Case 1: Unix socket binding
    if [ -n "$UDS" ]; then
        if check_uds_health "$UDS"; then
            exit 0
        else
            exit 1
        fi
    fi

    # Case 2: Direct HTTP/HTTPS binding
    if [ -n "$CERTFILE" ] && [ -n "$KEYFILE" ] && [ -f "$CERTFILE" ] && [ -f "$KEYFILE" ]; then
        # SSL certificates provided - use HTTPS
        if check_http_health "https" "127.0.0.1" "$PORT"; then
            exit 0
        else
            exit 1
        fi
    else
        # No SSL certificates - use HTTP
        if check_http_health "http" "127.0.0.1" "$PORT"; then
            exit 0
        else
            exit 1
        fi
    fi
}

main
