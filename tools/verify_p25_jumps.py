# -*- coding: utf-8 -*-
"""P25 验证：剧本 @jump 目标标签全部存在（4 结局路径闭环）。"""
import os, re, glob, sys

root = r'games/月光漫步'
gals = glob.glob(root + r'/章节/*.gal') + [root + r'/script.gal']
labels = set()
jumps = []
for g in gals:
    for i, line in enumerate(open(g, encoding='utf-8'), 1):
        s = line.strip()
        m = re.match(r'@label\s+(\S+)', s)
        if m:
            labels.add(m.group(1))
        m = re.match(r'@jump\s+(\S+)', s)
        if m:
            jumps.append((os.path.basename(g), i, m.group(1)))

bad = [(f, l, t) for f, l, t in jumps if t not in labels]
print('labels:', len(labels), 'jumps:', len(jumps), '无效跳转:', len(bad))
for f, l, t in bad:
    print(' ', f, l, t)
print('标签列表:', sorted(labels))
sys.exit(1 if bad else 0)
