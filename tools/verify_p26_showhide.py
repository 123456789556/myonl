# -*- coding: utf-8 -*-
"""P26-B4：@show/@hide 配对 + @cg 资源引用核查。"""
import os, re, glob, sys

root = r'games/月光漫步'
gals = glob.glob(root + r'/章节/*.gal') + [root + r'/script.gal']
imgs = set(os.path.splitext(f)[0] for f in os.listdir(root + '/images'))
shows, hides, cgs = [], [], []
for g in gals:
    for i, line in enumerate(open(g, encoding='utf-8'), 1):
        s = line.strip()
        m = re.match(r'@show\s+(\S+)', s)
        if m:
            shows.append((os.path.basename(g), i, m.group(1)))
        m = re.match(r'@hide\s*(\S*)', s)
        if m:
            hides.append((os.path.basename(g), i, m.group(1) or '*'))
        m = re.match(r'@cg\s+(\S+)', s)
        if m:
            cgs.append((os.path.basename(g), i, m.group(1)))

print('@show 次数:', len(shows), ' @hide 次数:', len(hides), ' @cg 次数:', len(cgs))
# @cg 资源存在性
missing_cg = [c for c in cgs if c[2] not in imgs and ('cg_' + c[2]) not in imgs]
print('缺失 @cg 资源:', len(missing_cg))
for c in missing_cg:
    print(' ', c)
# 列出全部 @cg
print('全部 @cg 解锁点:')
for c in cgs:
    print(' ', c[0] + ':' + str(c[1]), c[2])
# 粗略配对检查：各文件 show 与 hide 计数
print('--- 每文件 show/hide 计数 ---')
for g in gals:
    n = os.path.basename(g)
    sc = sum(1 for s in shows if s[0] == n)
    hc = sum(1 for h in hides if h[0] == n)
    print(f'  {n}: show={sc} hide={hc}')
sys.exit(1 if missing_cg else 0)
