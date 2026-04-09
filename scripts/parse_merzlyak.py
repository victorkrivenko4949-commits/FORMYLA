#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Merzlyak Problem Database Generator
Generates math problems in Merzlyak textbook style (levels 1-5)
With comprehensive error handling and validation
"""

import json
import random
import sys
import os
from typing import List, Dict, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MerzlyakGenerator:
    """Generator for Merzlyak-style math problems"""
    
    def __init__(self):
        self.problems = []
        self.problem_id = 1
        self.failed_generations = 0
        self.validation_failures = 0
    
    def generate_arithmetic_problem(self, level: int) -> Optional[Dict]:
        """
        Generate arithmetic problem based on level
        Level 1: Simple addition/subtraction
        Level 2: Multiplication/division
        Level 3: Multi-step operations
        Level 4: Fractions and decimals
        Level 5: Complex expressions
        
        Returns None if generation fails (for error handling demonstration)
        """
        try:
            if level == 1:
                # Simple addition/subtraction
                a = random.randint(1, 50)
                b = random.randint(1, 50)
                op = random.choice(['+', '-'])
                
                if op == '+':
                    answer = a + b
                    text = f"Вычислите: {a} + {b}"
                else:
                    # Ensure positive result
                    if a < b:
                        a, b = b, a
                    answer = a - b
                    text = f"Вычислите: {a} - {b}"
                
            elif level == 2:
                # Multiplication/division
                if random.choice([True, False]):
                    a = random.randint(2, 12)
                    b = random.randint(2, 12)
                    answer = a * b
                    text = f"Вычислите: {a} × {b}"
                else:
                    b = random.randint(2, 12)
                    answer = random.randint(1, 20)
                    a = answer * b
                    text = f"Вычислите: {a} : {b}"
            
            elif level == 3:
                # Multi-step operations
                a = random.randint(5, 20)
                b = random.randint(2, 10)
                c = random.randint(1, 15)
                
                operations = [
                    (f"({a} + {b}) × {c}", (a + b) * c),
                    (f"{a} × {b} + {c}", a * b + c),
                    (f"{a} × ({b} + {c})", a * (b + c)),
                ]
                
                expr, answer = random.choice(operations)
                text = f"Вычислите: {expr}"
            
            elif level == 4:
                # Fractions and decimals
                if random.choice([True, False]):
                    # Decimal operations
                    a = round(random.uniform(1, 10), 1)
                    b = round(random.uniform(1, 10), 1)
                    op = random.choice(['+', '-', '×'])
                    
                    if op == '+':
                        answer = round(a + b, 2)
                        text = f"Вычислите: {a} + {b}"
                    elif op == '-':
                        if a < b:
                            a, b = b, a
                        answer = round(a - b, 2)
                        text = f"Вычислите: {a} - {b}"
                    else:
                        answer = round(a * b, 2)
                        text = f"Вычислите: {a} × {b}"
                else:
                    # Simple fractions
                    num1 = random.randint(1, 5)
                    den1 = random.randint(2, 8)
                    num2 = random.randint(1, 5)
                    
                    answer = round(num1 / den1 + num2, 2)
                    text = f"Вычислите: {num1}/{den1} + {num2}"
            
            else:  # level == 5
                # Complex expressions
                a = random.randint(10, 50)
                b = random.randint(2, 10)
                c = random.randint(5, 20)
                d = random.randint(2, 8)
                
                operations = [
                    (f"({a} + {b}) × {c} - {d}", (a + b) * c - d),
                    (f"{a} - ({b} × {c} + {d})", a - (b * c + d)),
                    (f"({a} - {b}) × ({c} + {d})", (a - b) * (c + d)),
                ]
                
                expr, answer = random.choice(operations)
                text = f"Вычислите: {expr}"
            
            # Validation: ensure text and answer are valid
            if not text or answer is None:
                raise ValueError("Invalid problem generated")
            
            return {
                'id': self.problem_id,
                'text': text,
                'answer': str(answer),
                'level': level,
                'subject': 'arithmetic',
                'source': 'merzlyak_style'
            }
        
        except Exception as e:
            # Error handling: log and return None
            self.failed_generations += 1
            print(f"  ⚠ Failed to generate level {level} problem: {e}")
            return None
    
    def generate_algebra_problem(self, level: int) -> Optional[Dict]:
        """Generate algebra problems"""
        try:
            if level <= 2:
                # Simple equations
                x = random.randint(1, 20)
                b = random.randint(1, 30)
                a = random.randint(2, 10)
                
                result = a * x + b
                text = f"Решите уравнение: {a}x + {b} = {result}"
                answer = x
            
            elif level == 3:
                # Two-step equations
                x = random.randint(1, 15)
                a = random.randint(2, 8)
                b = random.randint(1, 20)
                c = random.randint(1, 15)
                
                result = a * x + b
                text = f"Решите уравнение: {a}x + {b} = {result + c}"
                answer = round((result + c - b) / a, 2)
            
            else:  # level >= 4
                # More complex equations
                x = random.randint(2, 10)
                a = random.randint(2, 6)
                b = random.randint(1, 10)
                c = random.randint(1, 8)
                
                left = a * x + b
                right = c * x
                text = f"Решите уравнение: {a}x + {b} = {c}x"
                answer = round(b / (c - a), 2) if c != a else x
            
            if not text or answer is None:
                raise ValueError("Invalid algebra problem")
            
            return {
                'id': self.problem_id,
                'text': text,
                'answer': str(answer),
                'level': level,
                'subject': 'algebra',
                'source': 'merzlyak_style'
            }
        
        except Exception as e:
            self.failed_generations += 1
            print(f"  ⚠ Failed to generate algebra level {level}: {e}")
            return None
    
    def generate_geometry_problem(self, level: int) -> Optional[Dict]:
        """Generate geometry problems"""
        try:
            if level <= 2:
                # Perimeter and area of rectangles
                a = random.randint(3, 15)
                b = random.randint(3, 15)
                
                if random.choice([True, False]):
                    answer = 2 * (a + b)
                    text = f"Найдите периметр прямоугольника со сторонами {a} см и {b} см."
                else:
                    answer = a * b
                    text = f"Найдите площадь прямоугольника со сторонами {a} см и {b} см."
            
            elif level == 3:
                # Triangle perimeter
                a = random.randint(5, 12)
                b = random.randint(5, 12)
                c = random.randint(5, 12)
                
                # Ensure triangle inequality
                if a + b <= c or a + c <= b or b + c <= a:
                    sides = sorted([a, b, c])
                    c = sides[0] + sides[1] - 1
                
                answer = a + b + c
                text = f"Найдите периметр треугольника со сторонами {a} см, {b} см и {c} см."
            
            else:  # level >= 4
                # Circle circumference or area
                r = random.randint(3, 10)
                
                if random.choice([True, False]):
                    answer = round(2 * 3.14 * r, 2)
                    text = f"Найдите длину окружности радиусом {r} см. (π ≈ 3.14)"
                else:
                    answer = round(3.14 * r * r, 2)
                    text = f"Найдите площадь круга радиусом {r} см. (π ≈ 3.14)"
            
            if not text or answer is None:
                raise ValueError("Invalid geometry problem")
            
            return {
                'id': self.problem_id,
                'text': text,
                'answer': str(answer),
                'level': level,
                'subject': 'geometry',
                'source': 'merzlyak_style'
            }
        
        except Exception as e:
            self.failed_generations += 1
            print(f"  ⚠ Failed to generate geometry level {level}: {e}")
            return None
    
    def validate_problem(self, problem: Dict) -> bool:
        """
        Validate problem structure and content
        Returns False for broken problems
        """
        try:
            # Check required fields
            required_fields = ['id', 'text', 'answer', 'level', 'subject']
            for field in required_fields:
                if field not in problem:
                    raise ValueError(f"Missing field: {field}")
            
            # Check text is not empty
            if not problem['text'] or len(problem['text'].strip()) < 5:
                raise ValueError("Text too short or empty")
            
            # Check answer is not empty
            if not problem['answer'] or problem['answer'].strip() == '':
                raise ValueError("Answer is empty")
            
            # Check level is valid
            if not isinstance(problem['level'], int) or problem['level'] < 1 or problem['level'] > 5:
                raise ValueError(f"Invalid level: {problem['level']}")
            
            # Check subject is valid
            valid_subjects = ['arithmetic', 'algebra', 'geometry']
            if problem['subject'] not in valid_subjects:
                raise ValueError(f"Invalid subject: {problem['subject']}")
            
            return True
        
        except Exception as e:
            self.validation_failures += 1
            print(f"  ✗ Validation failed for problem {problem.get('id', '?')}: {e}")
            return False
    
    def generate_database(self, total_problems: int = 100) -> List[Dict]:
        """
        Generate complete problem database
        Distributes problems across subjects and levels
        """
        print("=" * 70)
        print("MERZLYAK PROBLEM DATABASE GENERATOR")
        print("=" * 70)
        
        subjects = [
            ('arithmetic', self.generate_arithmetic_problem),
            ('algebra', self.generate_algebra_problem),
            ('geometry', self.generate_geometry_problem)
        ]
        
        problems_per_subject = total_problems // len(subjects)
        problems_per_level = problems_per_subject // 5
        
        print(f"\nTarget: {total_problems} problems")
        print(f"Distribution: {problems_per_subject} per subject, {problems_per_level} per level\n")
        
        for subject_name, generator_func in subjects:
            print(f"Generating {subject_name} problems...")
            
            for level in range(1, 6):
                generated = 0
                attempts = 0
                max_attempts = problems_per_level * 3  # Allow retries
                
                while generated < problems_per_level and attempts < max_attempts:
                    attempts += 1
                    
                    try:
                        problem = generator_func(level)
                        
                        if problem is None:
                            continue
                        
                        # Validate problem
                        if self.validate_problem(problem):
                            self.problems.append(problem)
                            self.problem_id += 1
                            generated += 1
                    
                    except Exception as e:
                        print(f"  ✗ Unexpected error at level {level}: {e}")
                        continue
                
                print(f"  Level {level}: {generated}/{problems_per_level} problems generated")
        
        print(f"\n✓ Total problems generated: {len(self.problems)}")
        print(f"⚠ Failed generations: {self.failed_generations}")
        print(f"✗ Validation failures: {self.validation_failures}")
        
        return self.problems
    
    def save_to_json(self, filepath: str) -> bool:
        """
        Save problems to JSON file with proper error handling
        Uses 'with' statement to ensure file descriptor is closed
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Write with proper encoding and file closure
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.problems, f, ensure_ascii=False, indent=2)
            
            # Verify file was written
            if not os.path.exists(filepath):
                raise IOError(f"File was not created: {filepath}")
            
            file_size = os.path.getsize(filepath)
            print(f"\n✓ Saved to: {filepath}")
            print(f"✓ File size: {file_size} bytes")
            print(f"✓ Problems in file: {len(self.problems)}")
            
            return True
        
        except IOError as e:
            print(f"\n✗ File I/O error: {e}")
            return False
        except Exception as e:
            print(f"\n✗ Unexpected error saving file: {e}")
            return False


def main():
    """Main execution function"""
    try:
        generator = MerzlyakGenerator()
        
        # Generate 100 problems (can be adjusted)
        problems = generator.generate_database(total_problems=100)
        
        if not problems:
            print("\n✗ No problems generated!")
            sys.exit(1)
        
        # Save to JSON
        output_path = os.path.join('data', 'merzlyak_db.json')
        success = generator.save_to_json(output_path)
        
        if not success:
            print("\n✗ Failed to save database!")
            sys.exit(1)
        
        print("\n" + "=" * 70)
        print("✅ GENERATION COMPLETE")
        print("=" * 70)
        
        # Show sample problems
        print("\nSample problems:")
        for i, problem in enumerate(problems[:3], 1):
            print(f"\n{i}. [{problem['subject'].upper()} - Level {problem['level']}]")
            print(f"   Text: {problem['text']}")
            print(f"   Answer: {problem['answer']}")
        
        sys.exit(0)
    
    except KeyboardInterrupt:
        print("\n\n⚠ Generation interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
