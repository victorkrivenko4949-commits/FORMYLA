#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify difficulty context mapping implementation.
Generates a few test tasks to ensure the system works correctly.
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from ai.deepseek_client import DeepSeekClient
from generators.grade_6_7_generator import Grade6_7Generator
from generators.grade_8_generator import Grade8Generator
from generators.grade_10_11_generator import Grade10_11Generator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_difficulty_context():
    """Test that difficulty context is properly integrated."""
    
    print("="*70)
    print("TESTING DIFFICULTY CONTEXT MAPPING")
    print("="*70)
    
    # Test the static method directly
    from generators.base_generator import TaskGenerator
    
    print("\n1. Testing get_difficulty_context() method:")
    print("-" * 70)
    for level in range(1, 8):
        context = TaskGenerator.get_difficulty_context(level)
        print(f"Level {level}: {context[:80]}...")
    
    print("\n2. Testing task generation with difficulty context:")
    print("-" * 70)
    
    # Initialize client
    client = DeepSeekClient()
    
    # Test with grade 6-7 generator
    generator = Grade6_7Generator(client)
    
    # Generate one test task with difficulty level 7
    print("\nGenerating test task (Grade 6-7, Difficulty 7)...")
    print("This should produce a VERY HARD task (Заключительный этап Всероса)")
    
    task = generator.generate_task(
        topic="Алгебра",
        subtopic="текстовые_задачи",
        difficulty=7,
        previous_tasks=[]
    )
    
    if task:
        print("\n✅ Task generated successfully!")
        print(f"Topic: {task.get('topic')}")
        print(f"Subtopic: {task.get('subtopic')}")
        print(f"Difficulty: {task.get('difficulty')}")
        print(f"Text: {task.get('text')[:150]}...")
        print(f"Answer: {task.get('answer')}")
        print(f"Solution: {task.get('solution')[:150]}...")
    else:
        print("\n❌ Task generation failed!")
        return False
    
    print("\n" + "="*70)
    print("TEST COMPLETED SUCCESSFULLY")
    print("="*70)
    return True


if __name__ == "__main__":
    try:
        success = test_difficulty_context()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        sys.exit(1)
