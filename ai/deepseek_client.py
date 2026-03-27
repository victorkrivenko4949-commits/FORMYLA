#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DeepSeek API Client with Exponential Backoff and Retry Logic
Provides reliable communication with DeepSeek API for content generation.
"""

import os
import sys
import time
import json
import logging
import requests
from typing import Optional, Dict, Any

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DeepSeekAPIError(Exception):
    """Custom exception for DeepSeek API errors."""
    pass


class DeepSeekClient:
    """
    Client for DeepSeek API with automatic retry and exponential backoff.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize DeepSeek client.
        
        Args:
            api_key: DeepSeek API key. If None, reads from DEEPSEEK_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get('DEEPSEEK_API_KEY')
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not provided and not found in environment")
        
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
        self.max_retries = 5
        self.base_delay = 2  # seconds
        self.timeout = 60  # seconds
        
    def generate(
        self, 
        prompt: str, 
        system_prompt: str = "", 
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> str:
        """
        Generate text using DeepSeek API with retry logic.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text
            
        Raises:
            DeepSeekAPIError: If all retries failed
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}: Sending request to DeepSeek API")
                
                response = requests.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                # Check HTTP status
                if response.status_code == 200:
                    data = response.json()
                    
                    # Validate response structure
                    if 'choices' in data and len(data['choices']) > 0:
                        content = data['choices'][0].get('message', {}).get('content')
                        if content:
                            logger.info("✓ Request successful")
                            return content
                        else:
                            logger.warning("Response missing content field")
                            raise ValueError("Invalid response structure")
                    else:
                        logger.warning("Response missing choices field")
                        raise ValueError("Invalid response structure")
                
                elif response.status_code == 429:
                    # Rate limit - wait longer
                    wait_time = 60
                    logger.warning(f"Rate limit (429). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                elif response.status_code in [500, 502, 503, 504]:
                    # Server error - retry with backoff
                    wait_time = self.base_delay * (2 ** attempt)
                    logger.warning(f"Server error ({response.status_code}). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                elif response.status_code == 401:
                    # Authentication error - no retry
                    logger.error("Authentication failed (401). Check API key.")
                    raise DeepSeekAPIError(f"Authentication failed: {response.text}")
                
                else:
                    # Other error
                    logger.error(f"HTTP {response.status_code}: {response.text}")
                    raise DeepSeekAPIError(f"HTTP {response.status_code}: {response.text}")
                    
            except requests.exceptions.Timeout:
                wait_time = self.base_delay * (2 ** attempt)
                logger.warning(f"Timeout. Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                
            except requests.exceptions.ConnectionError as e:
                wait_time = self.base_delay * (2 ** attempt)
                logger.warning(f"Connection error: {e}. Waiting {wait_time}s...")
                time.sleep(wait_time)
                
            except ValueError as e:
                # Invalid JSON or structure
                wait_time = self.base_delay * (2 ** attempt)
                logger.warning(f"Invalid response: {e}. Waiting {wait_time}s...")
                time.sleep(wait_time)
        
        # All retries exhausted
        logger.error(f"All {self.max_retries} retries exhausted")
        raise DeepSeekAPIError(f"Failed after {self.max_retries} attempts")


class CheckpointManager:
    """
    Manager for saving and loading generation progress.
    """
    
    def __init__(self, checkpoint_file: str = "checkpoint.json"):
        """
        Initialize checkpoint manager.
        
        Args:
            checkpoint_file: Path to checkpoint file
        """
        self.checkpoint_file = checkpoint_file
        
    def load(self) -> Dict[str, Any]:
        """
        Load checkpoint data from file.
        
        Returns:
            Checkpoint data dict or empty dict if file doesn't exist
        """
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Loaded checkpoint: {len(data.get('processed', []))} items processed")
                    return data
            except Exception as e:
                logger.error(f"Failed to load checkpoint: {e}")
                return {}
        return {}
    
    def save(self, data: Dict[str, Any]):
        """
        Save checkpoint data to file.
        
        Args:
            data: Checkpoint data to save
        """
        try:
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Checkpoint saved: {len(data.get('processed', []))} items")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            raise
    
    def clear(self):
        """Remove checkpoint file."""
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
            logger.info("Checkpoint cleared")


# Test block
if __name__ == '__main__':
    print("=" * 60)
    print("DeepSeek Client Test")
    print("=" * 60)
    
    # Test with invalid API key to demonstrate retry logic
    print("\n[TEST 1] Testing with INVALID API key (should fail after retries)...")
    try:
        client = DeepSeekClient(api_key="invalid_key_for_testing")
        result = client.generate("Сколько будет 2+2?")
        print(f"Result: {result}")
    except DeepSeekAPIError as e:
        print(f"\n[OK] Expected error caught: {e}")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
    
    print("\n" + "=" * 60)
    print("\n[TEST 2] Testing CheckpointManager...")
    
    # Test checkpoint manager
    checkpoint = CheckpointManager("test_checkpoint.json")
    
    # Save test data
    test_data = {
        'processed': [1, 2, 3, 4, 5],
        'last_id': 5,
        'timestamp': time.time()
    }
    checkpoint.save(test_data)
    print("[OK] Checkpoint saved")
    
    # Load test data
    loaded = checkpoint.load()
    print(f"[OK] Checkpoint loaded: {loaded}")
    
    # Clear
    checkpoint.clear()
    print("[OK] Checkpoint cleared")
    
    print("\n" + "=" * 60)
    print("Tests complete!")
    print("=" * 60)
