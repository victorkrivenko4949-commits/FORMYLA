#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Тестирование API бесплатного пробника с пошаговой генерацией
"""

import requests
import json
import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

BASE_URL = "http://localhost:5001"

def test_api_structure():
    """Проверка структуры API"""
    print("\n" + "="*60)
    print("TEST: API Structure Check")
    print("="*60)
    
    endpoints = [
        "/api/free_mock/generate_block",
        "/api/free_mock/evaluate"
    ]
    
    for endpoint in endpoints:
        url = f"{BASE_URL}{endpoint}"
        print(f"\nChecking endpoint: {endpoint}")
        
        try:
            # Try GET request (should return 405 Method Not Allowed or 401)
            response = requests.get(url)
            print(f"   GET: {response.status_code} (expected 401 or 405)")
            
            # Try POST without data
            response = requests.post(url, json={})
            print(f"   POST (empty): {response.status_code}")
            
        except Exception as e:
            print(f"   ERROR: {e}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("FREE MOCK API TESTING")
    print("="*60)
    print("Note: Full testing requires authentication")
    print("These tests check endpoint availability")
    print("="*60)
    
    test_api_structure()
    
    print("\n" + "="*60)
    print("TESTING COMPLETE")
    print("="*60)
    print("\nFor full testing:")
    print("   1. Open browser and go to http://localhost:5000")
    print("   2. Login")
    print("   3. Navigate to /free_mock/start")
    print("   4. Complete the test through the interface")
