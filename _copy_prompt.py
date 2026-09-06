# -*- coding: utf-8 -*-
import io, glob, os

# найти файл с "наставник" в имени
for f in glob.glob(r'C:\Users\Redmi\Downloads\*.md'):
    base = os.path.basename(f)
    if 'наставник' in base.lower() or ('roo' in base.lower() and os.path.getsize(f) > 30000):
        # скопировать в рабочий каталог с ASCII-именем
        dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_atlas_tutor_prompt.md')
        import shutil
        shutil.copyfile(f, dst)
        print('COPIED:', repr(base), os.path.getsize(f))
