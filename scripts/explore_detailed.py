#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Detailed exploration of problems.ru structure.
"""

import requests
from bs4 import BeautifulSoup
import sys
import codecs

# Fix Windows console encoding
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def explore_detailed(problem_id):
    """Get detailed HTML structure for a problem."""
    url = f"https://problems.ru/view_problem_details_new.php?id={problem_id}"
    
    print(f"Fetching: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            return
        
        # Try different encodings
        for encoding in ['koi8-r', 'utf-8', 'windows-1251']:
            try:
                response.encoding = encoding
                soup = BeautifulSoup(response.text, 'html.parser')
                
                print(f"\n{'='*70}")
                print(f"Encoding: {encoding}")
                print(f"{'='*70}")
                
                # Get title
                title = soup.find('title')
                if title:
                    print(f"Title: {title.get_text(strip=True)}")
                
                # Get all text content
                body = soup.find('body')
                if body:
                    # Get all divs
                    divs = body.find_all('div')
                    print(f"\nFound {len(divs)} div elements")
                    
                    for i, div in enumerate(divs[:10], 1):
                        classes = div.get('class', [])
                        text = div.get_text(strip=True)[:150]
                        if text:
                            print(f"\n[Div {i}] class={classes}")
                            print(f"  Text: {text}...")
                
                # Save full HTML to file for inspection
                with open(f'data/problem_{problem_id}_{encoding}.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"\nSaved full HTML to: data/problem_{problem_id}_{encoding}.html")
                
                break
                
            except Exception as e:
                print(f"Error with {encoding}: {e}")
                continue
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test with a few problem IDs
    for pid in [1, 100, 1000, 10000]:
        explore_detailed(pid)
        print("\n" + "="*70 + "\n")
