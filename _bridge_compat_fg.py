# -*- coding: utf-8 -*-
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

os.environ['NATS_URL'] = 'nats://192.168.99.11:4222'
os.environ['H2_ROO_SESSION_MAP_PATH'] = 'C:/ProgramData/H2/state/session_map.json'
os.environ['OWUI_BASE_URL'] = 'https://chat.h2platform.ru'
os.environ['H2_BRIDGE_LEGACY_DUAL_PUBLISH'] = '0'
os.chdir('C:/ProgramData/H2/config')

# Apply the exact compat patch from bridge_compat_runner.py
from datetime import timedelta
from types import SimpleNamespace
from nats.js.kv import KeyValue

def apply_bucket_status_compatibility():
    status_type = KeyValue.BucketStatus
    if hasattr(status_type, "config"):
        return
    def config(status):
        ttl = getattr(status, "ttl", None)
        converted = timedelta(seconds=float(ttl)) if ttl is not None else None
        return SimpleNamespace(ttl=converted)
    status_type.config = property(config)

apply_bucket_status_compatibility()

import runpy
runpy.run_module('owui_roo_bridge', run_name='__main__', alter_sys=True)
