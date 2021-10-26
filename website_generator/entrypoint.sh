#!/bin/sh

while true; do
    echo "Updating links..."
    python links_updater/links_updater.py
    echo "Running pelican..."
    pelican -e DELETE_OUTPUT_DIRECTORY=''
    echo "Sleeping..."
    sleep 1h
done