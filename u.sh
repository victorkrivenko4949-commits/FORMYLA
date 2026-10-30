#!/bin/bash
set -e
cd /opt/formyla
if [ ! -d .git ]; then
  git init
  git remote add origin https://github.com/victorkrivenko4949-commits/FORMYLA.git
fi
git fetch origin main
git reset --hard origin/main
systemctl restart formyla
echo "=== DONE! FORMYLA UPDATED TO LATEST MAIN ==="
