import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)) or '.')
path = 'app.py'
with open(path, 'rb') as f:
    content = f.read()

old = b"    if request.args.get('scope'):\r\n        session['olyad_scope'] = request.args.get('scope')\r\n    return render_template('olympiad_test_select_class.html')"

new = b"    if request.args.get('scope'):\r\n        session['olyad_scope'] = request.args.get('scope')\r\n    session.modified = True\r\n    return render_template('olympiad_test_select_class.html')"

content = content.replace(old, new)
with open(path, 'wb') as f:
    f.write(content)

with open(path, 'rb') as f:
    v = f.read()
if b'session.modified' in v:
    print('OK')
else:
    print('FAIL')
