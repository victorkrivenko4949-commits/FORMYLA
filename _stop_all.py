# -*- coding: utf-8 -*-
import io, sys, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

ps = (
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Select-Object ProcessId,CommandLine | Format-List | Out-String"
)
try:
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    out.write(r.stdout)
except Exception as e:
    out.write('err %s\n' % e)

open('_stop_all.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
