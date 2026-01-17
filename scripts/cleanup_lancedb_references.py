#!/usr/bin/env python3
"""
Script to remove all LanceDB and Ingestion Lambda references from the codebase.
This script will identify and list all files that need to be cleaned up.
"""

import os
import re
import sys
from pathlib import Path

def find_files_with_patterns(root_dir, patterns, exclude_dirs=None):
    """Find all files containing any of the given patterns."""
    if exclude_dirs is None:
        exclude_dirs = ['.git', '__pycache__', 'node_modules', 'venv', '.venv']
    
    matches = {}
    root_path = Path(root_dir)
    
    for file_path in root_path.rglob('*'):
        if file_path.is_file() and not any(exclude in str(file_path) for exclude in exclude_dirs):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    file_matches = []
                    
                    for pattern_name, pattern in patterns.items():
                        if re.search(pattern, content, re.IGNORECASE):
                            lines = content.split('\n')
                            for i, line in enumerate(lines, 1):
                                if re.search(pattern, line, re.IGNORECASE):
                                    file_matches.append((pattern_name, i, line.strip()))
                    
                    if file_matches:
                        matches[str(file_path.relative_to(root_path))] = file_matches
                        
            except Exception as e:
                print(f"Error reading {file_path}: {e}")
    
    return matches

def main():
    # Define patterns to search for
    patterns = {
        'lancedb': r'lancedb|lance_db|LanceDB',
        'ingestion_lambda': r'ingestion.lambda|IngestionLambda|INGESTION_LAMBDA',
        'lambda_arn': r'INGESTION_LAMBDA_ARN|IngestionLambdaArn',
    }
    
    # Find all files with these patterns
    root_dir = Path(__file__).parent.parent
    matches = find_files_with_patterns(root_dir, patterns)
    
    print("=" * 80)
    print("LanceDB and Ingestion Lambda References Cleanup Report")
    print("=" * 80)
    
    if not matches:
        print("No references found!")
        return
    
    for file_path, file_matches in sorted(matches.items()):
        print(f"\n📁 {file_path}")
        print("-" * len(file_path))
        
        grouped_matches = {}
        for pattern_name, line_num, line_content in file_matches:
            if pattern_name not in grouped_matches:
                grouped_matches[pattern_name] = []
            grouped_matches[pattern_name].append((line_num, line_content))
        
        for pattern_name, lines in grouped_matches.items():
            print(f"  🔍 {pattern_name.upper()}:")
            for line_num, line_content in lines[:5]:  # Show first 5 matches
                print(f"    Line {line_num}: {line_content}")
            if len(lines) > 5:
                print(f"    ... and {len(lines) - 5} more matches")
    
    print(f"\n📊 Summary: Found references in {len(matches)} files")
    
    # Files that should be completely removed
    files_to_remove = [
        'concierge/lambda_src/ingestion_lambda_function.py',
        'concierge/lambda_src/ingestion_lambda_function_new.py', 
        'concierge/lambda_deployment/ingestion_lambda_function.py',
        'concierge/lambda_src/Dockerfile',  # If it's only for ingestion lambda
        'concierge/lambda_src/requirements.txt',  # If it's only for ingestion lambda
    ]
    
    print("\n🗑️  Files that should be completely removed:")
    for file_path in files_to_remove:
        if os.path.exists(os.path.join(root_dir, file_path)):
            print(f"  - {file_path}")
    
    print(f"\n✅ Run this script to see what needs to be cleaned up.")
    print(f"   Next step: Remove references and files manually or with targeted edits.")

if __name__ == "__main__":
    main() 