#!/bin/sh

set -e

while true; do
    echo "Updating links..."
    uv run links_updater/links_updater.py
    echo "Running pelican..."
    uv run pelican
    echo "Sleeping..."
    sleep 1h
done
