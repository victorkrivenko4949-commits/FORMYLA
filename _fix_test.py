# -*- coding: utf-8 -*-
with open('tests/test_task_bank.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix line 397-404: test_clamp_below_min
for i in range(len(lines)):
    if i >= 396 and i <= 403 and 'test_clamp_below_min' in lines[i] or (
        i >= 397 and i <= 404 and 'clamp' in lines[min(i-1, len(lines)-1)].lower()):
        pass  # search range

# Find and fix the specific area
for i, line in enumerate(lines):
    if line.strip().startswith('def test_clamp_below_min'):
        target = i
        break

new_block = [
    '    def test_clamp_below_min(self):\n',
    '        """Уровень < 1 зажимается в 1."""\n',
    '        profile = {\n',
    '            "topics_full": [\n',
    '                {"target_level": 0, "calibration": False},\n',
    '            ],\n',
    '        }\n',
    '        assert tb.pick_bank_level(profile) == tb.MIN_BANK_LEVEL\n',
    '\n',
]

# Replace the block
end = target
for j in range(target, min(target + 10, len(lines))):
    if 'test_custom_default' in lines[j] or 'def test_' in lines[j+1] if j+1 < len(lines) else False:
        end = j - 1
        break

# Find the actual end (next def or blank+before next def)
end = target + 1
while end < len(lines) and not lines[end].strip().startswith('def test_'):
    end += 1
end -= 1

lines[target:end+1] = new_block

with open('tests/test_task_bank.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"Fixed lines {target+1}-{end+1}")
