try:
    from olympiads_restored import OLYMPIADS_DB
    total_problems = sum(len(c.get('problems', [])) for c in OLYMPIADS_DB)
    print(f'V olympiads_restored.py: {len(OLYMPIADS_DB)} probnikov, {total_problems} zadach')
    print('Fajl gotov!')
except Exception as e:
    print(f'Fajl eshe ne gotov: {e}')
