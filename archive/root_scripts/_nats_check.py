# -*- coding: utf-8 -*-
import asyncio, io, sys, json, nats
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    nc = await nats.connect('nats://192.168.99.11:4222', connect_timeout=5)
    js = nc.jetstream()
    # Check ownership KV
    try:
        kv = await js.key_value('owui_roo_bridge_victor_ownership')
        status = await kv.status()
        print('OWNERSHIP_KV history=', getattr(status, 'history', None), 'ttl=', getattr(status, 'ttl', None))
        try:
            entry = await kv.get('owner')
            print('OWNER_ENTRY:', entry.value.decode('utf-8', 'replace')[:300])
        except Exception as e:
            print('OWNER_GET_ERR:', str(e)[:200])
    except Exception as e:
        print('OWNERSHIP_KV_ERR:', str(e)[:200])

    # Request route_attest on node-scoped command subject
    corr = 'diag-' + str(asyncio.get_event_loop().time())[-8:]
    subject = 'h2.roo_bridge.node.victor.cmd.route_attest'
    reply = nc.new_inbox()
    sub = await nc.subscribe(reply)
    payload = json.dumps({
        'operation': 'route_attest', 'node': 'victor', 'corr_id': corr,
        'workspace': 'C:/H2/victor_bridge_canary',
    }).encode()
    await nc.publish(subject, payload, reply=reply)
    try:
        msg = await sub.next_msg(timeout=15)
        print('REPLY:', msg.data.decode('utf-8', 'replace')[:500])
    except Exception as e:
        print('NO_REPLY:', str(e)[:100])
    await nc.close()

asyncio.run(main())
