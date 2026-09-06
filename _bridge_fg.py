# -*- coding: utf-8 -*-
import asyncio, io, sys, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

os.environ['NATS_URL'] = 'nats://192.168.99.11:4222'
os.environ['H2_ROO_SESSION_MAP_PATH'] = 'C:/ProgramData/H2/state/session_map.json'
os.environ['OWUI_BASE_URL'] = 'https://chat.h2platform.ru'
os.environ['H2_BRIDGE_LEGACY_DUAL_PUBLISH'] = '0'
os.environ['H2_NODE_CONFIG'] = 'C:/ProgramData/H2/config/node.json'
os.chdir('C:/ProgramData/H2/config')

import runpy
runpy.run_module('owui_roo_bridge', run_name='__main__', alter_sys=True)
