#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Find valid problem IDs from problems.ru catalog.
"""

import requests
from bs4 import BeautifulSoup
import sys
import codecs
import re

# Fix Windows console encoding
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def find_problem_ids():
    """Find valid problem IDs from the catalog."""
    
    # Try the subject catalog
    catalog_url = "https://problems.ru/view_by_subject_new.php?parent="
    
    print(f"Exploring catalog: {catalog_url}")
    
    try:
        response = requests.get(catalog_url, timeout=10)
        response.encoding = 'koi8-r'
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all links
            links = soup.find_all('a', href=True)
            
            problem_ids = set()
            
            for link in links:
                href = link.get('href')
                
                # Look for problem detail links
                match = re.search(r'view_problem_details_new\.php\?id=(\d+)', href)
                if match:
                    problem_ids.add(int(match.group(1)))
                
                # Look for other problem link patterns
                match = re.search(r'id=(\d+)', href)
                if match and 'problem' in href.lower():
                    problem_ids.add(int(match.group(1)))
            
            print(f"\nFound {len(problem_ids)} unique problem IDs")
            
            if problem_ids:
                sorted_ids = sorted(problem_ids)[:20]
                print(f"First 20 IDs: {sorted_ids}")
                
                # Test first valid ID
                if sorted_ids:
                    test_id = sorted_ids[0]
                    test_url = f"https://problems.ru/view_problem_details_new.php?id={test_id}"
                    print(f"\nTesting first ID: {test_url}")
                    
                    test_response = requests.get(test_url, timeout=10)
                    test_response.encoding = 'koi8-r'
                    test_soup = BeautifulSoup(test_response.text, 'html.parser')
                    
                    # Save for inspection
                    with open(f'data/valid_problem_{test_id}.html', 'w', encoding='utf-8') as f:
                        f.write(test_response.text)
                    
                    print(f"Saved HTML to: data/valid_problem_{test_id}.html")
                    
                    # Try to find problem text
                    print(f"\nSearching for problem content...")
                    
                    # Look for tables with problem data
                    tables = test_soup.find_all('table')
                    print(f"Found {len(tables)} tables")
                    
                    for i, table in enumerate(tables, 1):
                        text = table.get_text(strip=True)[:300]
                        if len(text) > 50 and 'задач' in text.lower():
                            print(f"\n[Table {i}] Potential problem content:")
                            print(f"  {text}...")
                    
                    # Look for specific divs
                    for class_name in ['problemtext', 'problem_text', 'pbody', 'content', 'main']:
                        elem = test_soup.find('div', class_=class_name)
                        if elem:
                            print(f"\nFound div.{class_name}:")
                            print(f"  {elem.get_text(strip=True)[:200]}...")
            
            else:
                print("No problem IDs found in catalog")
                
                # Save catalog HTML for manual inspection
                with open('data/catalog.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print("Saved catalog HTML to: data/catalog.html")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    find_problem_ids()
