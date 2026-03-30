#!/bin/bash
set -e

BASE_DIR=${BASE_DIR:-/mnt/data}

echo "=== sim-generation-app ==="
echo "BASE_DIR: ${BASE_DIR}"
if [ -n "${HOST_DATA_DIR:-}" ]; then
    echo "HOST_DATA_DIR: ${HOST_DATA_DIR}"
fi
echo "Python: $(python --version 2>&1)"
echo "sct.so: $(find /app/trajectory -name 'sct*.so' 2>/dev/null || echo 'NOT FOUND')"


python pipeline.py --base-dir "${BASE_DIR}" "$@"
