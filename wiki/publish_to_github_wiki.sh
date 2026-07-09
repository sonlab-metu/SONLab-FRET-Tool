#!/usr/bin/env bash
#
# Publish the wiki/ source in this folder to the GitHub Wiki of the public repo.
#
# Prerequisite (one time): the wiki Git repository must already exist. Enable it
# under the repository's Settings > Features > Wikis, then create any first page
# in the browser ("Create the first page" > Save). After that, this script can
# clone and update the wiki repository.
#
# Usage:
#   ./publish_to_github_wiki.sh                # uses the default repo below
#   WIKI_REMOTE=git@github.com:OWNER/REPO.wiki.git ./publish_to_github_wiki.sh
#
set -euo pipefail

# Default to the public repository's wiki.
WIKI_REMOTE="${WIKI_REMOTE:-git@github.com:sonlab-metu/SONLab-FRET-Tool.wiki.git}"

# This script lives in the wiki source folder.
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "Cloning wiki repository: $WIKI_REMOTE"
if ! git clone --quiet "$WIKI_REMOTE" "$WORK_DIR/wiki" 2>/dev/null; then
    echo
    echo "ERROR: could not clone the wiki repository."
    echo "The wiki must be initialized first:"
    echo "  1. Open the repository on GitHub > Settings > Features and tick 'Wikis'."
    echo "  2. Open the Wiki tab, click 'Create the first page', and Save."
    echo "  3. Re-run this script."
    exit 1
fi

echo "Copying pages (excluding the repo-side README.md)..."
find "$SRC_DIR" -maxdepth 1 -name '*.md' ! -name 'README.md' -exec cp {} "$WORK_DIR/wiki/" \;

echo "Copying images..."
mkdir -p "$WORK_DIR/wiki/images"
find "$SRC_DIR/images" -maxdepth 1 -type f ! -name 'README.md' -exec cp {} "$WORK_DIR/wiki/images/" \;

cd "$WORK_DIR/wiki"
git add -A
if git diff --cached --quiet; then
    echo "No changes to publish; the wiki is already up to date."
    exit 0
fi

git commit --quiet -m "Update user guide"
git push --quiet
echo "Done. The wiki has been updated."
