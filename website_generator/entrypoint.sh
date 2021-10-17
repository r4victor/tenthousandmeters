#!/bin/sh

while true; do
    python links_updater/links_updater.py
    pelican -e DELETE_OUTPUT_DIRECTORY=''
    sleep 1m
done