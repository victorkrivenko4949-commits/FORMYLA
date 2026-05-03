#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the 3 remaining pipeline service files."""
import base64, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "services", "daily_pool")

# Each file is stored as base64 below (generated separately)
# We decode and write them

FILES = {}

# Will be populated by running with --encode flag
# For now, just write directly using triple-quoted strings with no f-strings

def write_all():
    write_embedder()
    write_polisher()
    write_meta_reviewer()
    print("Done: 3 pipeline services written.")

def write_embedder():
    p = os.path.join(OUT, "embedder.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write(EMBEDDER_SRC)
    print(f"  embedder.py ({len(EMBEDDER_SRC)} bytes)")

def write_polisher():
    p = os.path.join(OUT, "polisher.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write(POLISHER_SRC)
    print(f"  polisher.py ({len(POLISHER_SRC)} bytes)")

def write_meta_reviewer():
    p = os.path.join(OUT, "meta_reviewer.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write(META_REVIEWER_SRC)
    print(f"  meta_reviewer.py ({len(META_REVIEWER_SRC)} bytes)")


###############################################################################
# SOURCE CODE CONSTANTS
###############################################################################

EMBEDDER_SRC = ""
POLISHER_SRC = ""
META_REVIEWER_SRC = ""

if __name__ == "__main__":
    write_all()
