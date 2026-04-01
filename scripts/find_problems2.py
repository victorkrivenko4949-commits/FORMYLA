#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Find valid problem IDs by exploring subject pages.
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

def explore_subject_page(subject_id):
    """Explore a subject page to find problem links."""
    
    url = f"https://problems.ru/view_by_subject_new.php?parent={subject_id}"
    print(f"\nExploring subject page: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        response.encoding = 'koi8-r'
        
        if response.status_code != 200:
            print(f"Failed: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all links
        links = soup.find_all('a', href=True)
        
        problem_ids = []
        
        for link in links:
            href = link.get('href')
            
            # Look for problem links
            if 'view_problem' in href or 'id=' in href:
                match = re.search(r'id=(\d+)', href)
                if match:
                    pid = int(match.group(1))
                    if pid not in problem_ids and pid < 1000000:  # Reasonable ID range
                        problem_ids.append(pid)
                        print(f"  Found problem ID: {pid} in {href}")
        
        return problem_ids
        
    except Exception as e:
        print(f"Error: {e}")
        return []

def test_problem_id(problem_id):
    """Test if a problem ID is valid and extract its content."""
    
    url = f"https://problems.ru/view_problem_details_new.php?id={problem_id}"
    print(f"\nTesting problem ID {problem_id}: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        response.encoding = 'koi8-r'
        
        if response.status_code != 200:
            print(f"  Status: {response.status_code}")
            return False
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check if it's an error page
        error_div = soup.find('div', class_='componentboxheader')
        if error_div and 'Ошибка' in error_div.get_text():
            print(f"  Error page - problem not found")
            return False
        
        # Look for problem content
        content_div = soup.find('div', class_='componentboxcontents')
        if content_div:
            text = content_div.get_text(strip=True)
            if len(text) > 50:
                print(f"  SUCCESS! Found content ({len(text)} chars)")
                print(f"  Preview: {text[:200]}...")
                
                # Save HTML
                with open(f'data/valid_problem_{problem_id}.html', 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"  Saved to: data/valid_problem_{problem_id}.html")
                
                return True
        
        print(f"  No content found")
        return False
        
    except Exception as e:
        print(f"  Error: {e}")
        return False

def main():
    """Main exploration."""
    
    print("="*70)
    print("Finding valid problems from problems.ru")
    print("="*70)
    
    # Explore algebra subject (ID 88 from catalog)
    print("\n1. Exploring Algebra subject (ID 88)...")
    algebra_ids = explore_subject_page(88)
    
    # Explore geometry subject (ID 193 from catalog)
    print("\n2. Exploring Geometry subject (ID 193)...")
    geometry_ids = explore_subject_page(193)
    
    # Combine all found IDs
    all_ids = list(set(algebra_ids + geometry_ids))
    print(f"\n{'='*70}")
    print(f"Total unique problem IDs found: {len(all_ids)}")
    
    if all_ids:
        print(f"Sample IDs: {sorted(all_ids)[:10]}")
        
        # Test first few IDs
        print(f"\n{'='*70}")
        print("Testing problem IDs...")
        print(f"{'='*70}")
        
        valid_ids = []
        for pid in sorted(all_ids)[:10]:
            if test_problem_id(pid):
                valid_ids.append(pid)
                if len(valid_ids) >= 3:  # Stop after finding 3 valid problems
                    break
        
        print(f"\n{'='*70}")
        print(f"Valid problem IDs: {valid_ids}")
        print(f"{'='*70}")
    else:
        print("No problem IDs found. Site structure may have changed.")

if __name__ == "__main__":
    main()
