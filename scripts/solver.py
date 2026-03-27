#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Olympiad Solution Generator for FORMYLA Platform
Generates detailed solutions for 4383 olympiad problems using DeepSeek API.
"""

import os
import sys
import json
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.deepseek_client import DeepSeekClient, CheckpointManager, DeepSeekAPIError
from olympiads import OLYMPIADS_DB

# Configuration
TEST_MODE = True  # Set to False for full generation
TEST_LIMIT = 3    # Number of solutions to generate in test mode

OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "generated_solutions.jsonl")
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "solver_checkpoint.json")


def generate_solution(client: DeepSeekClient, problem_text: str, problem_answer: str) -> str:
    """
    Generate detailed solution using DeepSeek API.
    
    Args:
        client: DeepSeekClient instance
        problem_text: Problem statement
        problem_answer: Correct answer
        
    Returns:
        Generated solution text
        
    Raises:
        DeepSeekAPIError: If generation fails
    """
    system_prompt = """Ты опытный преподаватель олимпиадной математики. 
Твоя задача — написать максимально подробное, логичное и пошаговое решение для задачи. 
Тебе будут даны 'Условие' и 'Правильный ответ'. 
Твое решение должно строго приводить именно к этому ответу. 

Обязательно используй LaTeX-форматирование для формул (обрамляй их в $$). 
Структурируй решение по шагам.
Выводи ТОЛЬКО текст решения, без приветствий и лишних комментариев."""
    
    user_prompt = f"""Условие задачи:
{problem_text}

Правильный ответ: {problem_answer}

Напиши подробное пошаговое решение."""
    
    solution = client.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.5,
        max_tokens=2000
    )
    
    return solution


def main():
    """Main solver function."""
    print("=" * 70)
    print("FORMYLA Olympiad Solution Generator - DeepSeek API")
    print("=" * 70)
    
    if TEST_MODE:
        print(f"\n⚠️  TEST MODE: Will generate only {TEST_LIMIT} solutions")
    else:
        print("\n🚀 PRODUCTION MODE: Will generate all solutions")
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Initialize client and checkpoint
    try:
        client = DeepSeekClient()
        print("✓ DeepSeek client initialized")
    except ValueError as e:
        print(f"✗ Error: {e}")
        print("\nPlease set DEEPSEEK_API_KEY environment variable")
        return 1
    
    checkpoint = CheckpointManager(CHECKPOINT_FILE)
    checkpoint_data = checkpoint.load()
    processed = set(checkpoint_data.get('processed', []))
    
    print(f"✓ Checkpoint loaded: {len(processed)} solutions already processed")
    print(f"✓ Loaded olympiad database: {len(OLYMPIADS_DB)} olympiads")
    
    # Count total problems
    total_problems = sum(len(olympiad.get('problems', [])) for olympiad in OLYMPIADS_DB)
    print(f"✓ Total problems in database: {total_problems}")
    
    # Collect problems to process
    problems_to_process = []
    
    for olympiad in OLYMPIADS_DB:
        olympiad_id = olympiad.get('id')
        if not olympiad_id:
            continue
            
        for problem in olympiad.get('problems', []):
            problem_num = problem.get('num')
            problem_text = problem.get('text', '').strip()
            problem_answer = problem.get('answer', '').strip()
            
            # Skip if missing data
            if not problem_text or not problem_answer:
                continue
            
            # Create unique key
            problem_key = f"{olympiad_id}_{problem_num}"
            
            if problem_key not in processed:
                problems_to_process.append({
                    'olympiad_id': olympiad_id,
                    'problem_num': problem_num,
                    'text': problem_text,
                    'answer': problem_answer,
                    'key': problem_key
                })
    
    total_to_process = len(problems_to_process)
    print(f"\n📊 Problems to process: {total_to_process}")
    
    if TEST_MODE:
        problems_to_process = problems_to_process[:TEST_LIMIT]
        print(f"   (Limited to {TEST_LIMIT} for testing)")
    
    # Generation loop
    generated_count = 0
    failed_count = 0
    
    try:
        with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
            for i, problem_config in enumerate(problems_to_process, 1):
                print(f"\n[{i}/{len(problems_to_process)}] Generating solution...")
                print(f"  Olympiad ID: {problem_config['olympiad_id']}, Problem: {problem_config['problem_num']}")
                print(f"  Text preview: {problem_config['text'][:80]}...")
                
                try:
                    solution = generate_solution(
                        client,
                        problem_config['text'],
                        problem_config['answer']
                    )
                    
                    # Create result object
                    result = {
                        'olympiad_id': problem_config['olympiad_id'],
                        'problem_num': problem_config['problem_num'],
                        'solution': solution
                    }
                    
                    # Write to JSONL
                    f.write(json.dumps(result, ensure_ascii=False) + '\n')
                    f.flush()  # Force write to disk
                    
                    # Update checkpoint
                    processed.add(problem_config['key'])
                    checkpoint.save({
                        'processed': list(processed),
                        'generated_count': generated_count + 1
                    })
                    
                    generated_count += 1
                    print(f"  ✓ Solution generated and saved")
                    
                    # Small delay to avoid overwhelming API
                    time.sleep(1)
                    
                except DeepSeekAPIError as e:
                    print(f"  ✗ Failed: {e}")
                    failed_count += 1
                    
                except Exception as e:
                    print(f"  ✗ Unexpected error: {e}")
                    failed_count += 1
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Generation stopped by user (Ctrl+C)")
        print(f"Generated: {generated_count}, Failed: {failed_count}")
        print(f"Progress saved to checkpoint: {CHECKPOINT_FILE}")
        return 0
    
    # Final summary
    print("\n" + "=" * 70)
    print("GENERATION COMPLETE")
    print("=" * 70)
    print(f"✓ Generated: {generated_count}")
    print(f"✗ Failed: {failed_count}")
    print(f"📁 Output file: {OUTPUT_FILE}")
    print(f"💾 Checkpoint: {CHECKPOINT_FILE}")
    print("=" * 70)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
