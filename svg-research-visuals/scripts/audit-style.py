#!/usr/bin/env python3
# v2 样式静态审计闸门：检查每张示例 SVG 的无障碍属性、等宽数字、禁用旧色值/纯白底/Newsreader，
# 并报告状态色/风险色用量供人工复核（静态检查无法判断语义正确性，仅提示）。
# 用法：python3 scripts/audit-style.py    （返回码非 0 表示存在 FAIL）
import glob, html, os, re, sys

suite = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'examples', 'visual-smoke-suite')

# 禁用旧值（v1 → v2 迁移遗留）
FORBID = {
    '#fbfaf7': '旧页底（应为 #f6f2ea）',
    '#fffdf9': '旧卡片底（应为 #fffefb）',
    '#5fa45a': '旧冷绿状态色（应为 #5c9a84）',
    '#c96c5d': '旧状态红（应为 #c76a56）',
    '#ffffff': '纯白（研报图禁用）',
    '#dedbd3': '旧重边框（应改发丝线 #e6ded1）',
    '#9a5048': '旧风险令牌（应为 #9a5040）',
    '#c17a45': '旧重载色·分类1/主角/事实边条（应拆分为 #a67a52 / #bd6f33 / #9c5d28）',
    '#fff8e4': '旧核心判断强调底（应为 #f7eed6）',
    '#f7f1dc': '旧结论栏底（应为 #f7eed6）',
    '#f9ece8': '旧风险卡底（应为 #f7e9e3）',
    '#fdf6f3': '旧大面积风险面板底（应为 #fbf1ee）',
    '#24221e': '旧深炭（应为 #26231e）',
    '#9c5f2a': '旧强调赭（应为 #9c5d28）',
}
STATUS = {'#5c9a84': '状态绿', '#c76a56': '状态红'}
RISK = '#9a5040'
ALLOWED_SUITE_CANVASES = {
    (1600, 780), (1600, 900), (1600, 940), (1600, 1040), (1080, 1350),
}

def visible_text(source):
    parts = []
    for match in re.finditer(r'<(?:text|title|desc)\b[^>]*>(.*?)</(?:text|title|desc)>', source, re.I | re.S):
        value = re.sub(r'<[^>]+>', '', match.group(1))
        parts.append(html.unescape(value))
    return '\n'.join(parts)

fail = 0
files = sorted(glob.glob(os.path.join(suite, '*.svg')))
if not files:
    print('未找到 SVG：', suite); sys.exit(1)

for f in files:
    s = open(f, encoding='utf-8').read()
    low = s.lower()
    name = os.path.basename(f)
    errs = []
    if 'role="img"' not in s: errs.append('缺 role="img"')
    if 'aria-labelledby' not in s: errs.append('缺 aria-labelledby')
    if '<title' not in s: errs.append('缺 <title>')
    if '<desc' not in s: errs.append('缺 <desc>')
    canvas = re.search(r'<svg\b[^>]*\bviewBox=["\']0\s+0\s+(\d+)\s+(\d+)["\']', s, re.I)
    if not canvas:
        errs.append('缺有效 viewBox')
    elif tuple(map(int, canvas.groups())) not in ALLOWED_SUITE_CANVASES:
        errs.append('画布不在预设集合：%s×%s' % canvas.groups())
    if re.search(r'(?<=[\u4e00-\u9fff])[,;:]|[,;:](?=[\u4e00-\u9fff])', visible_text(s)):
        errs.append('中文语境使用半角逗号/分号/冒号（应使用全角）')
    if 'tnum' not in low: errs.append('未启用 tabular-nums(tnum)')
    if 'newsreader' in low: errs.append('仍引用 Newsreader（数字和 hero 数字应使用系统中文无衬线栈）')
    if re.search(r'<circle\b[^>]*fill=["\']#26231e["\']', low):
        errs.append('存在深炭实心圆（实际数据点应使用系列色；中性现价使用 #6a655c）')
    for hexv, why in FORBID.items():
        if hexv in low: errs.append('出现禁用色 %s（%s）' % (hexv, why))
    st = sum(low.count(h) for h in STATUS)
    rk = low.count(RISK)
    tag = 'FAIL' if errs else 'PASS'
    if errs: fail = 1
    print('%s %-28s | 状态色×%d 风险色×%d' % (tag, name, st, rk))
    for e in errs:
        print('    - ' + e)

print('\n提示：状态色仅用于明确改善/恶化，风险色仅用于风险/证伪左条与标题；请人工确认语义。')
sys.exit(fail)
