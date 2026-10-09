#!/usr/bin/env python3
import struct, os, sys

path = os.path.join(os.path.dirname(__file__), 'public', 'images', 'euler', 
                    'euler_2009_tasks.pdf', 'euler_2009_regional_g8_n2_p1_cropde2ac903.png')

print(f"Checking: {path}")
print(f"Exists: {os.path.exists(path)}")
print(f"Size: {os.path.getsize(path)} bytes")

with open(path, 'rb') as f:
    header = f.read(8)
    print(f"PNG signature: {header.hex()}")
    print(f"Is valid PNG: {header == b'\\x89PNG\\r\\n\\x1a\\n'}")
    
    # Read chunk length and type
    length_data = f.read(4)
    chunk_len = struct.unpack('>I', length_data)[0]
    chunk_type = f.read(4)
    print(f"First chunk: {chunk_type}, length: {chunk_len}")
    
    if chunk_type == b'IHDR':
        width = struct.unpack('>I', f.read(4))[0]
        height = struct.unpack('>I', f.read(4))[0]
        bit_depth = f.read(1)[0]
        color_type = f.read(1)[0]
        print(f"Width: {width}, Height: {height}")
        print(f"Bit depth: {bit_depth}, Color type: {color_type}")
    
    # Count total chunks
    f.seek(8)
    chunks = 0
    while True:
        len_b = f.read(4)
        if not len_b or len(len_b) < 4:
            break
        length = struct.unpack('>I', len_b)[0]
        typ = f.read(4)
        if not typ or len(typ) < 4:
            break
        chunks += 1
        if chunks <= 5 or typ == b'IEND':
            print(f"  Chunk {chunks}: {typ}, length={length}")
        f.seek(length + 4, os.SEEK_CUR)  # skip data + crc
    
    print(f"Total chunks: {chunks}")

print("Done")
