"""Quick test to check LaTeX in the HTML response."""
import requests
import re

r = requests.get('http://127.0.0.1:5001/secrets', timeout=30)
c = r.text
print('Status:', r.status_code)
print('Length:', len(c))
print('Has katex.min.js:', 'katex.min.js' in c)
print('Has auto-render.min.js:', 'auto-render.min.js' in c)
print('Has renderMathInElement(document.body):', 'renderMathInElement(document.body' in c)
print('Has textbookContent:', 'textbookContent' in c)

# Dollar signs
dollar_count = c.count('$')
print('Total $ signs:', dollar_count)

# Check for escaped dollars
escaped = '\\$' in c
print('Has escaped \\$:', escaped)

# Check for $$ signs (display math)
double_dollar = '$$' in c
print('Has double $$:', double_dollar)

# Sample first method content
idx = c.find('textbookContent')
if idx > 0:
    sample = c[idx:idx+1500]
    print('\n--- Sample around textbookContent ---')
    print(sample[:1000])
    print('---')
