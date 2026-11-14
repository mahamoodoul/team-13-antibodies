#!/usr/bin/env bash
# Publish the shortlist visualiser to the gh-pages branch, which GitHub Pages serves.
#
#   viz/publish.sh
#
# The site is built from the committed files at HEAD, so what goes live is always
# a commit someone can point to. The branch is generated, never edited by hand.
# It is assembled from git objects with a private index, so the working tree is
# not touched and no temporary checkout is made.
#
# Each publish replaces the branch with a fresh one-commit history. That is why
# the push is forced: the history of a generated site carries no meaning.
#
# Commit viz/ (and run viz/build_data.py if the pipeline changed) before publishing.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
export GIT_INDEX_FILE="$repo/.git/gh-pages.index"

git -C "$repo" read-tree --empty

# add <git object ref> <path in the published site>
add() {
  git -C "$repo" update-index --add --cacheinfo "100644,$(git -C "$repo" rev-parse "$1"),$2"
}

add HEAD:viz/index.html index.html
add HEAD:viz/designs.json designs.json
add HEAD:viz/scaffold/1N8Z.pdb scaffold/1N8Z.pdb

# An empty .nojekyll stops GitHub from running Jekyll over the site.
empty="$(git -C "$repo" hash-object -w --stdin </dev/null)"
git -C "$repo" update-index --add --cacheinfo "100644,$empty,.nojekyll"

tree="$(git -C "$repo" write-tree)"
commit="$(git -C "$repo" commit-tree "$tree" -m "Publish viz from $(git -C "$repo" rev-parse --short HEAD)")"
git -C "$repo" push --force origin "$commit:refs/heads/gh-pages"
echo "published $commit to gh-pages"
