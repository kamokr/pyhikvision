#!/usr/bin/env bash
echo ":: cleaning"
find -name '*.egg-info' -type d -print -exec rm -rf {} +
find -name '*.py?' -print -delete
find . -type d -empty -print -delete
rm -rf ./dist ./build