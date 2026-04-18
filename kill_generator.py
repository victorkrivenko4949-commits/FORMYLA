import os
import signal
import subprocess

# Find python process running mass_generator.py
result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV'], 
                       capture_output=True, text=True)

lines = result.stdout.strip().split('\n')
for line in lines[1:]:  # Skip header
    if 'python.exe' in line:
        parts = line.split(',')
        pid = int(parts[1].strip('"'))
        print(f"Found Python process: PID {pid}")
        try:
            os.kill(pid, signal.CTRL_C_EVENT)
            print(f"Sent CTRL_C_EVENT to PID {pid}")
        except Exception as e:
            print(f"Error: {e}")
