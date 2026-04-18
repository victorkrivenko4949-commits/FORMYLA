#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Migration script to convert olympiad problems to LaTeX format
Processes text and solution fields through LLM for intelligent math formatting
"""

import json
import time
import random
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.deepseek_client import DeepSeekClient
from olympiads import OLYMPIADS_DB


class OlympiadLatexMigrator:
    """Migrates olympiad problems to LaTeX format using LLM"""
    
    def __init__(self):
        self.client = DeepSeekClient()
        self.processed_count = 0
        self.failed_count = 0
        self.system_prompt = self._get_system_prompt()
    
    def _get_system_prompt(self) -> str:
        """System prompt for LLM to convert math to LaTeX"""
        return """Ты профессиональный математический редактор. Твоя единственная задача — найти в предоставленном тексте все математические переменные, числа, дроби, степени, корни и уравнения, и обернуть их в формат LaTeX со знаками доллара $.

КРИТИЧЕСКИЕ ПРАВИЛА:
1. **Индексы:** Преобразуй pn → $p_n$, qi → $q_i$, x1 → $x_1$
2. **Степени:** Преобразуй x^2 → $x^2$, p² → $p^2$, a³ → $a^3$
3. **Дроби:** Преобразуй a/b → $\\frac{a}{b}$ (только если это математическая дробь, не дата!)
4. **Корни:** Преобразуй sqrt(x) → $\\sqrt{x}$, √x → $\\sqrt{x}$
5. **Одиночные переменные:** Оборачивай в $: "Пусть x — скорость" → "Пусть $x$ — скорость"
6. **Математические операции:** ≥ → $\\geq$, ≤ → $\\leq$, · → $\\cdot$, ≠ → $\\neq$
7. **Греческие буквы:** α → $\\alpha$, β → $\\beta$, π → $\\pi$ и т.д.
8. **Уравнения:** Оборачивай полностью: "2x + 3 = 7" → "$2x + 3 = 7$"

КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:
- Менять, удалять или перефразировать русские слова
- Изменять структуру текста
- Добавлять или удалять предложения
- Менять числа или значения

ФОРМАТ ОТВЕТА:
Верни ТОЛЬКО обработанный текст без дополнительных комментариев, объяснений или markdown-разметки."""
    
    def convert_text_to_latex(self, text: str, max_retries: int = 3) -> str:
        """
        Convert mathematical notation in text to LaTeX format
        
        Args:
            text: Original text with plain math notation
            max_retries: Maximum number of retry attempts
            
        Returns:
            Text with LaTeX formatting
        """
        if not text or not text.strip():
            return text
        
        prompt = f"""Преобразуй математические выражения в этом тексте в формат LaTeX:

{text}

Верни ТОЛЬКО преобразованный текст, без комментариев."""
        
        for attempt in range(max_retries):
            try:
                response = self.client.generate(
                    prompt=prompt,
                    system_prompt=self.system_prompt,
                    temperature=0.3,  # Low temperature for consistency
                    max_tokens=4000
                )
                
                # Clean response
                response = response.strip()
                
                # Remove markdown code blocks if present
                if response.startswith('```'):
                    lines = response.split('\n')
                    response = '\n'.join(lines[1:-1]) if len(lines) > 2 else response
                
                return response
                
            except Exception as e:
                print(f"  ⚠️ Attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"  ⏳ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
        
        print(f"  ❌ Failed to convert after {max_retries} attempts, returning original")
        return text
    
    def migrate_problem(self, problem: dict) -> dict:
        """
        Migrate a single problem to LaTeX format
        
        Args:
            problem: Problem dictionary with 'text', 'answer', 'solution'
            
        Returns:
            Problem dictionary with LaTeX-formatted fields
        """
        migrated = problem.copy()
        
        # Convert text
        if 'text' in problem:
            print(f"    🔄 Converting problem text...")
            migrated['text_latex'] = self.convert_text_to_latex(problem['text'])
        
        # Convert solution
        if 'solution' in problem:
            print(f"    🔄 Converting solution...")
            migrated['solution_latex'] = self.convert_text_to_latex(problem['solution'])
        
        return migrated
    
    def migrate_olympiad(self, olympiad: dict) -> dict:
        """
        Migrate all problems in an olympiad
        
        Args:
            olympiad: Olympiad dictionary with 'problems' list
            
        Returns:
            Olympiad dictionary with migrated problems
        """
        migrated = olympiad.copy()
        migrated['problems'] = []
        
        for i, problem in enumerate(olympiad.get('problems', []), 1):
            print(f"  📝 Problem {i}/{len(olympiad['problems'])}: #{problem.get('num', '?')}")
            try:
                migrated_problem = self.migrate_problem(problem)
                migrated['problems'].append(migrated_problem)
                self.processed_count += 1
            except Exception as e:
                print(f"  ❌ Failed to migrate problem: {e}")
                migrated['problems'].append(problem)  # Keep original
                self.failed_count += 1
        
        return migrated
    
    def test_migration(self, num_samples: int = 3):
        """
        Test migration on random samples
        
        Args:
            num_samples: Number of random problems to test
        """
        print("=" * 80)
        print("ТЕСТОВЫЙ ПРОГОН МИГРАЦИИ В LATEX")
        print("=" * 80)
        
        # Collect all problems
        all_problems = []
        for olympiad in OLYMPIADS_DB:
            for problem in olympiad.get('problems', []):
                all_problems.append({
                    'olympiad': olympiad.get('olympiad_title', 'Unknown'),
                    'year': olympiad.get('year', '?'),
                    'grade': olympiad.get('grade', '?'),
                    'problem': problem
                })
        
        # Select random samples
        samples = random.sample(all_problems, min(num_samples, len(all_problems)))
        
        for i, sample in enumerate(samples, 1):
            print(f"\n{'=' * 80}")
            print(f"ТЕСТ {i}/{num_samples}")
            print(f"Олимпиада: {sample['olympiad']}, {sample['year']}, {sample['grade']} класс")
            print(f"Задача №{sample['problem'].get('num', '?')}")
            print("=" * 80)
            
            # Show original
            print("\n📄 ОРИГИНАЛ (Условие):")
            print("-" * 80)
            original_text = sample['problem'].get('text', '')
            print(original_text[:500] + ('...' if len(original_text) > 500 else ''))
            
            print("\n📄 ОРИГИНАЛ (Решение):")
            print("-" * 80)
            original_solution = sample['problem'].get('solution', '')
            print(original_solution[:500] + ('...' if len(original_solution) > 500 else ''))
            
            # Migrate
            print("\n🔄 Конвертация в LaTeX...")
            migrated = self.migrate_problem(sample['problem'])
            
            # Show converted
            print("\n✨ КОНВЕРТИРОВАНО В LATEX (Условие):")
            print("-" * 80)
            latex_text = migrated.get('text_latex', '')
            print(latex_text[:500] + ('...' if len(latex_text) > 500 else ''))
            
            print("\n✨ КОНВЕРТИРОВАНО В LATEX (Решение):")
            print("-" * 80)
            latex_solution = migrated.get('solution_latex', '')
            print(latex_solution[:500] + ('...' if len(latex_solution) > 500 else ''))
            
            # Analysis
            print("\n🔍 АНАЛИЗ ИЗМЕНЕНИЙ:")
            print("-" * 80)
            
            # Check for LaTeX markers
            has_dollars_text = '$' in latex_text
            has_dollars_solution = '$' in latex_solution
            
            print(f"✓ Знаки доллара в условии: {'ДА ✅' if has_dollars_text else 'НЕТ ❌'}")
            print(f"✓ Знаки доллара в решении: {'ДА ✅' if has_dollars_solution else 'НЕТ ❌'}")
            
            # Check for LaTeX commands
            latex_commands = ['\\frac', '\\sqrt', '\\cdot', '_', '^', '\\geq', '\\leq']
            found_in_text = [cmd for cmd in latex_commands if cmd in latex_text]
            found_in_solution = [cmd for cmd in latex_commands if cmd in latex_solution]
            
            if found_in_text:
                print(f"✓ LaTeX команды в условии: {', '.join(found_in_text)}")
            if found_in_solution:
                print(f"✓ LaTeX команды в решении: {', '.join(found_in_solution)}")
            
            print("\n" + "=" * 80)
        
        print(f"\n✅ Тестирование завершено!")
        print(f"Обработано задач: {self.processed_count}")
        print(f"Ошибок: {self.failed_count}")
    
    def migrate_all(self, batch_size: int = 10, output_file: str = 'olympiads_latex.json'):
        """
        Migrate all olympiads in batches
        
        Args:
            batch_size: Number of olympiads to process in one batch
            output_file: Output JSON file path
        """
        print("=" * 80)
        print("ПОЛНАЯ МИГРАЦИЯ БАЗЫ ОЛИМПИАД В LATEX")
        print("=" * 80)
        print(f"Всего олимпиад: {len(OLYMPIADS_DB)}")
        print(f"Размер батча: {batch_size}")
        print("=" * 80)
        
        migrated_db = []
        
        for i, olympiad in enumerate(OLYMPIADS_DB, 1):
            print(f"\n🏆 Олимпиада {i}/{len(OLYMPIADS_DB)}: {olympiad.get('olympiad_title', 'Unknown')}")
            print(f"   Год: {olympiad.get('year', '?')}, Класс: {olympiad.get('grade', '?')}")
            
            migrated = self.migrate_olympiad(olympiad)
            migrated_db.append(migrated)
            
            # Save checkpoint every batch_size olympiads
            if i % batch_size == 0:
                print(f"\n💾 Сохранение чекпоинта ({i} олимпиад)...")
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(migrated_db, f, ensure_ascii=False, indent=2)
                print(f"✅ Чекпоинт сохранен в {output_file}")
        
        # Final save
        print(f"\n💾 Сохранение финального результата...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(migrated_db, f, ensure_ascii=False, indent=2)
        
        print("\n" + "=" * 80)
        print("✅ МИГРАЦИЯ ЗАВЕРШЕНА!")
        print(f"Обработано задач: {self.processed_count}")
        print(f"Ошибок: {self.failed_count}")
        print(f"Результат сохранен в: {output_file}")
        print("=" * 80)


def main():
    """Main entry point"""
    migrator = OlympiadLatexMigrator()
    
    # Run test on 3 random problems
    # migrator.test_migration(num_samples=3)
    
    # Full migration:
    migrator.migrate_all(batch_size=10, output_file='olympiads_latex.json')


if __name__ == "__main__":
    main()
