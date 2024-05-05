#!/bin/sh

set -e

while true; do
    # echo "Updating links..."
    # python links_updater/links_updater.py
    echo "Running pelican..."
    pelican
    echo "Sleeping..."
    sleep 1h
done
