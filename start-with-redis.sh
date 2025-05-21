#!/bin/sh
set -e
REDIS_DATA_DIR="${REDIS_DATA_DIR:-/data/redis}"
mkdir -p "$REDIS_DATA_DIR"
redis-server --daemonize yes --dir "$REDIS_DATA_DIR"
exec "$@"
