#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to generate a new logic task with options field.
"""

import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.deepseek_client import DeepSeekClient
from generators.grade_6_7_generator import Grade6_7Generator

def test_generate_logic_task():
    """Generate a single logic task to verify options field."""
    print("="*70)
    print("TESTING NEW LOGIC TASK GENERATION WITH OPTIONS")
    print("="*70)
    
    # Initialize client and generator
    client = DeepSeekClient()
    generator = Grade6_7Generator(client)
    
    # Generate a logic task
    print("\n🔄 Generating logic task (Логика/Нестандартные)...")
    task = generator.generate_task(
        topic="Логика/Нестандартные",
        subtopic="логические_задачи",
        difficulty=2,
        previous_tasks=[]
    )
    
    if task:
        print("\n✅ Task generated successfully!")
        print("\n" + "="*70)
        print("GENERATED TASK JSON:")
        print("="*70)
        print(json.dumps(task, indent=2, ensure_ascii=False))
        print("="*70)
        
        # Check for options field
        if 'options' in task:
            print(f"\n✅ OPTIONS FIELD PRESENT: {task['options']}")
        else:
            print(f"\n❌ OPTIONS FIELD MISSING!")
        
        # Check for encoding instructions in text
        if '1 —' in task['text'] or '0 —' in task['text'] or 'введите' in task['text'].lower():
            print(f"\n❌ WARNING: Task contains encoding instructions!")
        else:
            print(f"\n✅ Task text is clean (no encoding instructions)")
            
    else:
        print("\n❌ Failed to generate task")

if __name__ == '__main__':
    test_generate_logic_task()
