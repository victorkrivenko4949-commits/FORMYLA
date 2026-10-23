# -*- coding: utf-8 -*-
import socket, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
out = open('_nats_diag.txt', 'w', encoding='utf-8')

def log(msg):
    out.write(msg + '\n')
    out.flush()
    print(msg)

for i in range(3):
    s = socket.socket()
    s.settimeout(6)
    try:
        r = s.connect_ex(('192.168.99.11', 4222))
        log(f'attempt {i}: connect_ex={r}')
        if r == 0:
            s.settimeout(6)
            try:
                data = s.recv(1024)
                log(f'  recv {len(data)} bytes: {data[:120]!r}')
            except socket.timeout:
                log('  recv TIMEOUT (no NATS INFO handshake)')
    except Exception as e:
        log(f'attempt {i}: ERROR {type(e).__name__} {e}')
    finally:
        s.close()

out.close()
