#!/usr/bin/env python3
"""批量提取 Notebook 代码格 -> Python 文件"""
import json
from pathlib import Path

notebooks_dir = Path('student_notebooks')
scripts_dir = Path('notebook_scripts')
scripts_dir.mkdir(exist_ok=True)

for nb_path in sorted(notebooks_dir.glob('*.ipynb')):
    py_path = scripts_dir / f'{nb_path.stem}.py'
    if py_path.exists():
        print(f'[跳过] {py_path.name} 已存在')
        continue
    
    with open(nb_path, encoding='utf-8') as f:
        nb = json.load(f)
    
    title_lines = []
    code_cells = []
    for cell in nb['cells']:
        if cell['cell_type'] == 'markdown':
            src = ''.join(cell['source'])
            if src.startswith('#') and not title_lines:
                title_lines = src.strip().split('\n')
        elif cell['cell_type'] == 'code':
            src = ''.join(cell['source']).strip()
            if src:
                code_cells.append(src)
    
    if not code_cells:
        print(f'[跳过] {nb_path.name} 无代码')
        continue
    
    chapter_num = nb_path.stem.split('_')[0]
    lines = [
        '#!/usr/bin/env python3',
        '# -*- coding: utf-8 -*-',
        '"""',
        f'从 {nb_path.name} 提取',
        '',
        f'--- {title_lines[0].lstrip("# ") if title_lines else nb_path.stem} ---',
        '"""',
        ''
    ]
    for i, code in enumerate(code_cells):
        if i > 0:
            lines.append('')
            lines.append('#' + '=' * 59)
            lines.append('')
        lines.append(code)
    
    lines.append('')
    lines.append('print("\n" + "=" * 60)')
    lines.append(f'print("\u2705 \u7b2c {chapter_num} \u7ae0 {nb_path.stem} \u4ee3\u7801\u5168\u90e8\u6267\u884c\u5b8c\u6bd5")')
    
    with open(py_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'[\u5df2\u521b\u5efa] {py_path.name}')

print('\n\u5168\u90e8\u5b8c\u6210\uff01')
