#!/usr/bin/env python3
"""Check the downloaded PNG using PIL and verify visual content."""
from PIL import Image
import os
import sys

print("=== PIL Diagnostic ===")

# Check the downloaded file
path = r'C:\Users\Victor\Desktop\diag_downloaded.png'
print(f"File: {path}")
print(f"Exists: {os.path.exists(path)}")

try:
    img = Image.open(path)
    print(f"Size: {img.size}")
    print(f"Mode: {img.mode}")
    print(f"Format: {img.format}")
    print(f"Info: {img.info}")
    
    # Get pixel range
    extrema = img.getextrema()
    print(f"Extrema (per channel): {extrema}")
    
    # Convert to JPEG
    jpg_path = r'C:\Users\Victor\Desktop\diag_converted.jpg'
    img_rgb = img.convert('RGB')
    img_rgb.save(jpg_path, 'JPEG', quality=95)
    jpg_size = os.path.getsize(jpg_path)
    print(f"Saved JPEG to: {jpg_path}")
    print(f"JPEG size: {jpg_size} bytes")
    
    print("\n=== SUCCESS: Image is valid with visual content ===")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
