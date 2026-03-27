#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Code Dump Generator for TEOREMA/Formyle Project
Safely collects all source code into a single Markdown file for analysis.
Implements smart truncation for large data files to prevent memory issues.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding issues
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Configuration
EXCLUDED_DIRS = {'venv', 'env', '.git', '__pycache__', '.vscode', 'node_modules', 'uploads'}
EXCLUDED_EXTENSIONS = {'.pyc', '.pyo', '.pyd', '.so', '.dll', '.exe', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg'}
TARGET_EXTENSIONS = {'.py', '.html', '.css', '.js'}
LARGE_FILE_THRESHOLD = 200 * 1024  # 200 KB
TRUNCATE_FILES = {'problems.py', 'olympiads.py'}  # Files that MUST be truncated
MAX_FILES = 1000  # Safety limit to prevent infinite loops
TRUNCATE_HEAD_LINES = 100  # First N lines to keep
TRUNCATE_TAIL_LINES = 20   # Last N lines to keep

# Language mapping for syntax highlighting
LANGUAGE_MAP = {
    '.py': 'python',
    '.html': 'html',
    '.css': 'css',
    '.js': 'javascript'
}


def should_exclude_dir(dir_name):
    """Check if directory should be excluded."""
    return dir_name in EXCLUDED_DIRS or dir_name.startswith('.')


def should_exclude_file(filepath):
    """Check if file should be excluded."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in EXCLUDED_EXTENSIONS


def get_file_size_safe(filepath):
    """Get file size safely, return 0 on error."""
    try:
        return os.path.getsize(filepath)
    except (OSError, PermissionError):
        return 0


def should_truncate_file(filepath, file_size):
    """Determine if file should be truncated."""
    filename = os.path.basename(filepath)
    
    # Specific files that MUST be truncated
    if filename in TRUNCATE_FILES:
        return True
    
    # Generic large file threshold
    if file_size > LARGE_FILE_THRESHOLD:
        return True
    
    return False


def read_file_safe(filepath):
    """
    Read file safely with UTF-8 encoding and error handling.
    Returns (lines, error_message).
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        return lines, None
    except PermissionError:
        return None, "Permission denied"
    except Exception as e:
        return None, str(e)


def truncate_lines(lines, filepath):
    """
    Truncate large files intelligently.
    Keep first TRUNCATE_HEAD_LINES and last TRUNCATE_TAIL_LINES.
    """
    total_lines = len(lines)
    
    if total_lines <= (TRUNCATE_HEAD_LINES + TRUNCATE_TAIL_LINES):
        return lines
    
    header = lines[:TRUNCATE_HEAD_LINES]
    footer = lines[-TRUNCATE_TAIL_LINES:]
    
    truncation_marker = [
        '\n',
        f'# ... [TRUNCATED: {total_lines} total lines, showing first {TRUNCATE_HEAD_LINES} and last {TRUNCATE_TAIL_LINES}] ...\n',
        f'# ... [ПРОПУЩЕНА ОСНОВНАЯ ЧАСТЬ ДАННЫХ - {total_lines - TRUNCATE_HEAD_LINES - TRUNCATE_TAIL_LINES} строк] ...\n',
        '\n'
    ]
    
    return header + truncation_marker + footer


def collect_files(root_dir):
    """
    Recursively collect all relevant files from the project.
    Returns list of (relative_path, absolute_path) tuples.
    """
    files = []
    file_count = 0
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Filter out excluded directories IN-PLACE
        dirnames[:] = [d for d in dirnames if not should_exclude_dir(d)]
        
        for filename in filenames:
            if file_count >= MAX_FILES:
                print(f"⚠️  Warning: Reached max file limit ({MAX_FILES})")
                return files
            
            filepath = os.path.join(dirpath, filename)
            ext = os.path.splitext(filename)[1].lower()
            
            # Check if file should be included
            if ext in TARGET_EXTENSIONS and not should_exclude_file(filepath):
                rel_path = os.path.relpath(filepath, root_dir)
                files.append((rel_path, filepath))
                file_count += 1
    
    return files


def generate_dump(root_dir, output_file):
    """
    Generate the code dump file.
    """
    print(f"🔍 Scanning project directory: {root_dir}")
    files = collect_files(root_dir)
    
    print(f"📁 Found {len(files)} files to process")
    
    total_size = 0
    processed_count = 0
    truncated_count = 0
    error_count = 0
    
    with open(output_file, 'w', encoding='utf-8') as out:
        # Write header
        out.write("# Project Code Dump - TEOREMA/Formyle Mathematics Platform\n\n")
        out.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        out.write(f"**Total Files:** {len(files)}\n")
        out.write(f"**Project Root:** `{root_dir}`\n\n")
        out.write("---\n\n")
        
        # Process each file
        for rel_path, abs_path in sorted(files):
            print(f"  Processing: {rel_path}")
            
            file_size = get_file_size_safe(abs_path)
            total_size += file_size
            
            # Read file
            lines, error = read_file_safe(abs_path)
            
            if error:
                out.write(f"## File: `{rel_path}`\n\n")
                out.write(f"```\n[ERROR: {error}]\n```\n\n")
                out.write("---\n\n")
                error_count += 1
                continue
            
            # Determine if truncation is needed
            needs_truncation = should_truncate_file(abs_path, file_size)
            
            if needs_truncation:
                lines = truncate_lines(lines, abs_path)
                truncated_count += 1
                print(f"    [TRUNCATED] (original: {file_size // 1024} KB)")
            
            # Get language for syntax highlighting
            ext = os.path.splitext(abs_path)[1].lower()
            language = LANGUAGE_MAP.get(ext, '')
            
            # Write to output
            out.write(f"## File: `{rel_path}`\n\n")
            out.write(f"```{language}\n")
            out.write(''.join(lines))
            if not lines or not lines[-1].endswith('\n'):
                out.write('\n')
            out.write("```\n\n")
            out.write("---\n\n")
            
            processed_count += 1
    
    return {
        'total_files': len(files),
        'processed': processed_count,
        'truncated': truncated_count,
        'errors': error_count,
        'total_size_kb': total_size // 1024,
        'output_size_kb': os.path.getsize(output_file) // 1024
    }


def main():
    """Main execution function."""
    print("=" * 60)
    print("Code Dump Generator - TEOREMA/Formyle Project")
    print("=" * 60)
    
    # Get project root (current directory)
    root_dir = os.getcwd()
    output_file = os.path.join(root_dir, 'project_code_dump.md')
    
    print(f"\n[*] Project root: {root_dir}")
    print(f"[*] Output file: {output_file}\n")
    
    try:
        stats = generate_dump(root_dir, output_file)
        
        print("\n" + "=" * 60)
        print("[SUCCESS] DUMP COMPLETE")
        print("=" * 60)
        print(f"Total files found:     {stats['total_files']}")
        print(f"Successfully processed: {stats['processed']}")
        print(f"Truncated files:       {stats['truncated']}")
        print(f"Errors encountered:    {stats['errors']}")
        print(f"Input size (approx):   {stats['total_size_kb']} KB")
        print(f"Output file size:      {stats['output_size_kb']} KB")
        print(f"\n[*] Output saved to: {output_file}")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
