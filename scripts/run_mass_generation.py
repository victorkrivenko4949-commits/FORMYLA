#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CLI Script for Mass Task Generation
Provides command-line interface for batch task generation.
"""

import sys
import os
import argparse
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mass_generator import MassTaskGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='FORMYLA Mass Task Generation System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 50 tasks per grade (default)
  python scripts/run_mass_generation.py
  
  # Generate 100 tasks per grade
  python scripts/run_mass_generation.py --tasks 100
  
  # Custom output file
  python scripts/run_mass_generation.py --output my_tasks.json
  
  # Generate 500 tasks per grade (production)
  python scripts/run_mass_generation.py --tasks 500 --output production_tasks.json
        """
    )
    
    parser.add_argument(
        '--tasks',
        type=int,
        default=50,
        help='Number of tasks to generate per grade (default: 50)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='generated_tasks.json',
        help='Output JSON file path (default: generated_tasks.json)'
    )
    
    parser.add_argument(
        '--grades',
        type=str,
        default='6-7,8,10-11',
        help='Comma-separated list of grades to generate (default: 6-7,8,10-11)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser.parse_args()


def main():
    """Main entry point for CLI script."""
    args = parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Print banner
    print("="*70)
    print(" " * 10 + "FORMYLA PRODUCTION MATRIX GENERATION")
    print("="*70)
    print(f"\n📋 Configuration:")
    print(f"   Output file:      {args.output}")
    print(f"   Grades:           {args.grades}")
    print(f"\n📊 Production Matrix (per grade):")
    print(f"   Topics:           6 (Алгебра, Геометрия, Комбинаторика, Теория чисел, Движение, Логика)")
    print(f"   Difficulty levels: 7 (от базового до Всероса)")
    print(f"   Tasks per cell:   12 (уникальных)")
    print(f"   Tasks per grade:  6 × 7 × 12 = 504")
    print(f"   Total expected:   {504 * len(args.grades.split(','))} tasks ({len(args.grades.split(','))} grades)")
    print("\n" + "="*70)
    print("\n⚠️  Press Ctrl+C at any time to gracefully stop generation")
    print("   (SafeJSONWriter will properly close with valid syntax)")
    print("   Estimated time: 2-4 hours (depends on API latency)\n")
    print("="*70)
    
    # Validate environment
    if not os.environ.get('DEEPSEEK_API_KEY'):
        print("\n❌ ERROR: DEEPSEEK_API_KEY not found in environment")
        print("   Please set it in .env file or export it:")
        print("   export DEEPSEEK_API_KEY=your_api_key_here")
        sys.exit(1)
    
    # Build configuration (tasks_per_grade ignored in production matrix mode)
    config = {
        'output_file': args.output,
        'grades': args.grades.split(',')
    }
    
    # Create generator and run
    try:
        generator = MassTaskGenerator(config)
        generator.generate_all()
        
        print("\n" + "="*70)
        print("🎉 Generation completed successfully!")
        print(f"📁 Output file: {args.output}")
        print("="*70)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Generation interrupted by user (Ctrl+C)")
        print("   JSON file has been properly closed.")
        logger.info("Generation interrupted by user")
        
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        logger.error(f"Generation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
