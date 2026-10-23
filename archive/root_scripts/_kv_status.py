# -*- coding: utf-8 -*-
import asyncio, io, sys, nats
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    nc = await nats.connect('nats://192.168.99.11:4222', connect_timeout=5)
    js = nc.jetstream()
    kv = await js.key_value('owui_roo_bridge_victor_ownership')
    status = await kv.status()
    print('status type:', type(status))
    print('dir(status) has ttl:', 'ttl' in dir(status))
    print('status.ttl:', getattr(status, 'ttl', '<MISSING>'))
    print('status.config:', getattr(status, 'config', '<MISSING>'))
    cfg = getattr(status, 'config', None)
    if cfg is not None:
        print('config type:', type(cfg))
        print('config.ttl:', getattr(cfg, 'ttl', '<MISSING>'))
        print('config.history:', getattr(cfg, 'history', '<MISSING>'))
    print('status.history:', getattr(status, 'history', '<MISSING>'))
    print('status backends:', getattr(status, 'backing_store', getattr(status, 'backingStore', '<MISSING>')))
    await nc.close()

asyncio.run(main())
