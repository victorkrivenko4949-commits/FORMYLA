import os, glob

expected = ['R0','R1','F0','P1','X8','P2','X10','P3','P4','D1','C11','D2','D3','I1','L1','K1','V11','P7','P5']
results = []
for code in expected:
    path = f'_recon/{code}.md'
    exists = os.path.exists(path)
    status = 'OTPISALSYa' if exists else 'NE OTPISALSYa'
    results.append(f'BLOCK {code}: {status}')
    print(f'BLOCK {code}: {status}')

with open('_recon/p6_chain_status.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))
