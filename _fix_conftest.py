# Fix tests/conftest.py:
# _db.drop_all() iterates ALL apps in _app_engines, destroying the temp-copy
# of the real DB.  Fix: pop the real app before drop_all, re-add after.
path = 'tests/conftest.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Step 1: import real app module  
old1 = "import sqlite3\nimport pytest\n\n"
new1 = "import sqlite3\nimport pytest\n\nimport app as _real_app_module\n\n"
if old1 in c:
    c = c.replace(old1, new1)

# Step 2: fix teardown
old2 = "    _db.session.remove()\n    _db.drop_all()\n    ctx.pop()"
new2 = """    _db.session.remove()
    # drop_all() would also DROP the real app's temp-copy tables.
    # Pop the real app first, drop, then re-add it.
    _real_engine_backup = _db._app_engines.pop(_real_app_module.app, None)
    _db.drop_all()
    if _real_engine_backup is not None:
        _db._app_engines[_real_app_module.app] = _real_engine_backup
    ctx.pop()"""

if old2 in c:
    c = c.replace(old2, new2)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    print('DONE')
else:
    print('OLD NOT FOUND:', repr(c[c.find('_db.drop_all')-20:c.find('_db.drop_all')+80]))
