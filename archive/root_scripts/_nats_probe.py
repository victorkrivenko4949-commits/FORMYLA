# -*- coding: utf-8 -*-
import asyncio, io, sys, nats
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def t():
    try:
        nc = await asyncio.wait_for(
            nats.connect('nats://192.168.99.11:4222', connect_timeout=5, allow_reconnect=False),
            timeout=15,
        )
        print('NATS_CONNECTED', nc.is_connected)
        await nc.close()
    except Exception as e:
        print('NATS_ERROR', type(e).__name__, str(e)[:300])

asyncio.run(t())
