#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Exploration script to investigate problems.ru HTML structure.
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

def explore_problem_url(url):
    """Explore a single problem URL and print its structure."""
    print(f"\n{'='*70}")
    print(f"Exploring: {url}")
    print(f"{'='*70}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch (status {response.status_code})")
            return False
        
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Print title
        title = soup.find('title')
        if title:
            print(f"\n📌 Page Title: {title.get_text(strip=True)}")
        
        # Look for common problem containers
        print(f"\n🔍 Searching for problem content...")
        
        # Try various selectors
        selectors = [
            ('div', 'problem_text'),
            ('div', 'pbody'),
            ('div', 'problem'),
            ('div', 'task'),
            ('div', 'content'),
            ('div', 'main'),
            ('table', None),
        ]
        
        for tag, class_name in selectors:
            if class_name:
                elements = soup.find_all(tag, class_=class_name)
                if elements:
                    print(f"\n✓ Found {len(elements)} <{tag} class='{class_name}'> elements")
                    for i, elem in enumerate(elements[:2], 1):
                        text = elem.get_text(strip=True)[:200]
                        print(f"  [{i}] {text}...")
            else:
                elements = soup.find_all(tag)
                if elements:
                    print(f"\n✓ Found {len(elements)} <{tag}> elements")
        
        # Look for answer/solution
        print(f"\nSearching for answer/solution...")
        answer_keywords = ['answer', 'solution']
        for keyword in answer_keywords:
            elements = soup.find_all(string=lambda t: t and keyword.lower() in t.lower())
            if elements:
                print(f"  Found '{keyword}' in {len(elements)} text nodes")
        
        # Print first 2000 chars of HTML for manual inspection
        print(f"\nHTML Preview (first 2000 chars):")
        print("-" * 70)
        print(response.text[:2000])
        print("-" * 70)
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Test multiple problem URLs."""
    
    # Test different URL patterns based on the form action
    test_urls = [
        "https://problems.ru/view_problem_details_new.php?id=1",
        "https://problems.ru/view_problem_details_new.php?id=100",
        "https://problems.ru/view_problem_details_new.php?id=1000",
        "https://problems.ru/view_problem_details_new.php?id=10000",
        "https://problems.ru/view_by_subject_new.php?parent=",  # Subject catalog
    ]
    
    print("Problems.ru Structure Explorer")
    print("="*70)
    
    for url in test_urls:
        success = explore_problem_url(url)
        if success:
            print(f"\n✅ Successfully explored: {url}")
            break
        else:
            print(f"\n❌ Failed: {url}")
    
    print(f"\n{'='*70}")
    print("Exploration complete")

if __name__ == "__main__":
    main()
