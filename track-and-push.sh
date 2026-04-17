#!/bin/bash
# This script is ignored by git.
# Runs the tracker and pushes to git ONLY IF mangas.json was modified.

set -e

cd "$(dirname "$0")"

# Run the Python tracker
if [ -x ".venv/bin/python" ]; then
    .venv/bin/python src/main.py
else
    python3 src/main.py
fi

# Check if mangas.json was modified by the tracker
if git diff --name-only | grep -q "mangas.json"; then
    echo "Changes detected! Committing to git..."
    git add mangas.json
    git commit -m "Chore: New chapter found, updating mangas.json"
    git push
    echo "mangas.json has been pushed to your repository."
else
    echo "No new chapters or mangas.json was already up to date. Nothing to push."
fi
