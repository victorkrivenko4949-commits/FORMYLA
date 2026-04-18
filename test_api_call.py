#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test DeepSeek API call"""

import asyncio
import aiohttp
import os
import sys
import traceback
from dotenv import load_dotenv

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = 'https://api.deepseek.com/v1/chat/completions'

async def test_api():
    print(f"API Key present: {bool(DEEPSEEK_API_KEY)}")
    print(f"API Key (first 10 chars): {DEEPSEEK_API_KEY[:10] if DEEPSEEK_API_KEY else 'None'}")
    
    test_text = "Вычислите: \\( x_2 + \\sqrt x \\)"
    
    async with aiohttp.ClientSession(
        headers={
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json'
        }
    ) as session:
        try:
            payload = {
                'model': 'deepseek-chat',
                'messages': [
                    {
                        'role': 'user',
                        'content': f'Fix LaTeX in: {test_text}'
                    }
                ],
                'temperature': 0.1,
                'max_tokens': 500
            }
            
            print(f"\nSending request to: {DEEPSEEK_API_URL}")
            print(f"Payload: {payload}")
            
            async with session.post(DEEPSEEK_API_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                print(f"\nResponse status: {response.status}")
                response_text = await response.text()
                print(f"Response text (first 500 chars): {response_text[:500]}")
                
                if response.status == 200:
                    data = await response.json()
                    print(f"\nSuccess! Response: {data}")
                else:
                    print(f"\nError response: {response_text}")
                    
        except Exception as e:
            print(f"\n❌ Exception: {type(e).__name__}: {e}")
            print(f"Traceback:\n{traceback.format_exc()}")

if __name__ == '__main__':
    asyncio.run(test_api())
