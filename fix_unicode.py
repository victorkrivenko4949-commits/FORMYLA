lines = open('services/task_validator.py','r',encoding='utf-8').readlines()
idx = next(i for i,l in enumerate(lines) if 'if not text:' in l and i > 155)
insert = [
    '    # Unicode math -> LaTeX (for tasks from _RAW_DB)\n',
    '    for u, l in [\n',
    '        (chr(0x221a), r"\\sqrt"),\n',
    '        (chr(0x2265), r"\\geq"),\n',
    '        (chr(0x2264), r"\\leq"),\n',
    '        (chr(0x2260), r"\\neq"),\n',
    '        (chr(0x2208