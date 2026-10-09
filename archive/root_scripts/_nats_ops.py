# -*- coding: utf-8 -*-
import asyncio, io, sys, json, nats, uuid
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def probe(nc, op):
    corr = uuid.uuid4().hex
    subject = f'h2.roo_bridge.node.victor.cmd.{op}'
    reply = nc.new_inbox()
    sub = await nc.subscribe(reply)
    payload = json.dumps({'operation': op, 'node': 'victor', 'corr_id': corr, 'workspace': 'C:/H2/victor_bridge_canary'}).encode()
    await nc.publish(subject, payload, reply=reply)
    try:
        msg = await sub.next_msg(timeout=15)
        print(f'{op}: REPLY={msg.data.decode("utf-8","replace")[:400]}')
    except Exception as e:
        print(f'{op}: NO_REPLY {e}')
    await sub.unsubscribe()

async def main():
    nc = await nats.connect('nats://192.168.99.11:4222', connect_timeout=5)
    for op in ['route_attest', 'health', 'versions', 'list_instances']:
        await probe(nc, op)
    await nc.close()

asyncio.run(main())
