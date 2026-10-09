# -*- coding: utf-8 -*-
import io, sys, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
out = io.StringIO()

# PowerShell: найти python-процессы с аргументами run_batch/_run_file2_full
ps = (
    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Select-Object ProcessId,CommandLine | "
    "Format-List | Out-String"
)
try:
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    out.write(r.stdout)
    out.write('ERR: ' + r.stderr)
except Exception as e:
    out.write('err %s\n' % e)

open('_kill_full_run.txt', 'w', encoding='utf-8').write(out.getvalue())
print(out.getvalue())
