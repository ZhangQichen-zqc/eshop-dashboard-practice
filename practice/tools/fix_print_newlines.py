#!/usr/bin/env python3
"""修复 print(" 后面直接跟了实际换行的语法错误"""
import re
from pathlib import Path

scripts_dir = Path('notebook_scripts')

for py_path in sorted(scripts_dir.glob('*.py')):
    with open(py_path, encoding='utf-8') as f:
        content = f.read()
    
    # 修复: print(" 后面跟实际换行 + " 的情况
    original = content
    content = re.sub(
        r'print\("\n[ ]*\+ "',
        'print("\\n" + "',
        content
    )
    
    if content != original:
        with open(py_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'[已修复] {py_path.name}')
    else:
        print(f'[无变化] {py_path.name}')

print('\n全部完成！')
