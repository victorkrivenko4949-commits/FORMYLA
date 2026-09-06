# -*- coding: utf-8 -*-
import socket, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

s = socket.socket()
s.settimeout(8)
try:
    s.connect(('192.168.99.11', 4222))
    print('TCP_CONNECTED')
    s.settimeout(8)
    try:
        data = s.recv(1024)
        print('RECEIVED', len(data), 'bytes:', repr(data[:200]))
    except socket.timeout:
        print('RECV_TIMEOUT: no NATS INFO handshake within 8s')
except Exception as e:
    print('CONNECT_ERROR', type(e).__name__, str(e))
finally:
    s.close()
