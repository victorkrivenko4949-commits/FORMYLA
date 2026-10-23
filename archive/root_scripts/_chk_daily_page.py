# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
t = open('templates/daily_tasks/daily_tasks_dashboard.html', encoding='utf-8').read()
i = t.find('автоматически')
open('_ctx.txt', 'w', encoding='utf-8').write(t[max(0,i-500):i+500])
print('written')
