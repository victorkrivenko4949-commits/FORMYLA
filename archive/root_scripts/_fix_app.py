import sys, os
target = sys.argv[1]
os.chdir(os.path.dirname(os.path.abspath(target)) or '.')
target = os.path.basename(target)

with open(target, 'rb') as f:
    content = f.read()

# Find the marker in bytes
marker = b'@app.route("/olympiad-test")\r\ndef olympiad_test_select_class():\r\n    """Step 1: Select grade (5-11)."""\r\n    return render_template('
end_marker = b"'olympiad_test_select_class.html')\r\n"

start = content.index(marker)
end = content.index(end_marker, start) + len(end_marker)

new_block = b'@app.route("/olympiad-test")\r\ndef olympiad_test_select_class():\r\n    """Step 1: Select grade (5-11).\r\n    Save test parameters from URL query into session (length, level_hint, scope)."""\r\n    if request.args.get(\'length\'):\r\n        session[\'olyad_length\'] = request.args.get(\'length\')\r\n    if request.args.get(\'level_hint\'):\r\n        session[\'olyad_level_hint\'] = request.args.get(\'level_hint\')\r\n    if request.args.get(\'scope\'):\r\n        session[\'olyad_scope\'] = request.args.get(\'scope\')\r\n    return render_template(\'olympiad_test_select_class.html\')\r\n'

content = content[:start] + new_block + content[end:]
with open(target, 'wb') as f:
    f.write(content)

# Verify
with open(target, 'rb') as f:
    verify = f.read()
if b'olyad_length' in verify:
    print('SUCCESS')
else:
    print('FAIL')
