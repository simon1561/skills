# -*- coding: utf-8 -*-
"""blank_lines 的反例测试集。每条都对应一个真实踩过或被复审指出的坑。
运行：python3 tests_blank_lines.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blank_lines import analyze

KEEP = frozenset()          # 一行都不该删

def D(*idx):                # 应当删除的空行行号（0 起）
    return frozenset(idx)

CASES = [
    ("短下划线 --",        "正文\n\n--\n", KEEP),
    ("短下划线 =",         "正文\n\n=\n", KEEP),
    ("分隔线 ---",         "正文\n\n---\n", KEEP),
    ("段落尾吞下划线",      "甲\n\n乙\n--\n", KEEP),
    ("段落尾吞波浪围栏",    "正文\n~~~\n代码甲\n\n代码乙\n~~~\n", KEEP),
    ("围栏内多个区段",      "正文\n~~~\n甲\n\n乙\n\n丙\n\n丁\n~~~\n", KEEP),
    ("段落尾吞引用",        "正文\n> 引用内容\n\n引用之外的正文。\n", KEEP),
    ("段落尾吞列表",        "正文\n- 列表内容\n\n列表之外的正文。\n", KEEP),
    ("无前导竖线表格",      "a | b\n--- | ---\nx | y\n\n表格外正文\n", KEEP),
    ("列表续行",           "- 列表项\n  续行\n\n列表外正文\n", KEEP),
    ("列表内缩进续段",      "- 项\n\n    续段\n甲\n\n乙\n", KEEP),
    ("引用惰性续行",        "> 引用第一行\n引用续行\n\n引用外正文\n", KEEP),
    ("单星号跨段",          "*alpha\n\nbeta*\n", KEEP),
    ("星号数偶但未配对",    "*甲 *乙\n\n丙* 丁*\n", KEEP),
    ("双星号数偶但未配对",  "**甲 **乙\n\n丙** 丁**\n", KEEP),
    ("下划线强调跨段",      "_alpha\n\nbeta_\n", KEEP),
    ("转义星号",           "*甲\\*\n\n\\*乙*\n", KEEP),
    ("反引号跨段",          "`alpha\n\nbeta`\n", KEEP),
    ("反引号串不等长",      "`甲```\n\n`乙```\n", KEEP),
    ("多行行内链接",        "[说明\n\n](https://example.com)\n", KEEP),
    ("单行链接引用定义",    "正文\n\n[ref]: /target\n\n参见 [ref]。\n", KEEP),
    ("链接定义后接标题串",  '[ref]: /target\n\n"标题"\n', KEEP),
    ("多行链接定义",        "正文\n\n[ref]:\n  /url\n", KEEP),
    ("八空格缩进代码",      "        alpha\n\n        beta\n", KEEP),
    ("嵌套围栏",           "````text\n```\nalpha\n\nbeta\n````\n", KEEP),
    ("围栏内缩进伪关闭",    "~~~\n代码甲\n    ~~~\n\n代码乙\n\n代码丙\n~~~\n", KEEP),
    ("公式块内空行",        "$$\na\n\nb\n$$\n", KEEP),
    ("HTML 块",           "<div>\n内部文字\n\n*外部强调*\n", KEEP),
    ("script 内假结束标签", '<script>\nconst s = "</style>";\n\n甲\n\n乙\n</script>\n', KEEP),
    ("处理指令跨空行",      "<?example\n甲\n\n乙\n\n?>\n", KEEP),
    ("硬换行两空格",        "正文一  \n\n正文二\n", KEEP),
    ("删除线跨段",          "~~甲\n\n乙~~\n", KEEP),
    ("高亮跨段",           "==甲\n\n乙==\n", KEEP),
    ("普通两段",           "正文一。\n\n正文二。\n", D(1)),
    ("加粗标签段",          "**甲。** 正文一。\n\n**乙。** 正文二。\n", D(1)),
    ("标题下方",           "## 标题\n\n正文。\n", D(1)),
    ("标点导致跨段强调",    "*a!*b\n\nc*!d*\n", KEEP),
    ("词内下划线",         "_a_b\n\nc_d_\n", KEEP),
    ("三连星剩余定界符",    "***a**\n\n**b***\n", KEEP),
    ("单列表格吞正文",      "| 列名 |\n| --- |\n| 数据 |\n\n表格外正文\n", KEEP),
    ("段中公式状态丢失",    "引言\n$$\na\n\nb\n\nc\n\nd\n$$\n", KEEP),
    ("段中注释状态丢失",    "引言\n%%\na\n\nb\n\nc\n\nd\n%%\n", KEEP),
    ("列表分支吞围栏",      "- 项\n~~~\n甲\n\n乙\n\n丙\n\n丁\n~~~\n", KEEP),
    ("引用分支吞围栏",      "> 引用\n~~~\n甲\n\n乙\n\n丙\n\n丁\n~~~\n", KEEP),
    ("链接定义分支吞围栏",  "[ref]: /target\n~~~\n甲\n\n乙\n\n丙\n\n丁\n~~~\n", KEEP),
    ("块 ID 范围改变",     "第一段。\n\n第二段。 ^ref\n", KEEP),
    ("标签后带空格",       "** 甲**乙\n\n** 丙**丁\n", KEEP),
    ("标签前带空格",       "**甲 **乙\n\n丙** 丁**\n", KEEP),
    ("缩进块后接围栏",      "    缩进代码\n```\n甲\n\n乙\n\n丙\n```\n", KEEP),
    ("Tab 缩进伪关闭围栏",  "```\n\t```\n甲\n\n乙\n```\n", KEEP),
    ("非行首注释",         "正文 %%\n\n甲\n\n乙\n\n%%\n", KEEP),
    ("列表行内开启注释",    "- 项目 %%\n\n甲\n\n乙\n\n%%\n", KEEP),
    ("标签结尾标点后接文字", "**甲！**乙\n\n**丙**丁\n", KEEP),
    ("段落续行开启注释",    "正文\n续行 %%\n\n甲\n\n乙\n\n%%\n", KEEP),
    ("列表续行开启注释",    "- 列表项\n续行 %%\n\n甲\n\n乙\n\n%%\n", KEEP),
    ("标签结尾标点后接空格", "**按期间计价。** 价格对应一个月。\n\n**非独占。** 同一时刻。\n",
                          D(1)),
    ("注释同行关闭再开启",  "%% 第一条注释 %% 正文 %%\n甲\n\n乙\n\n%%\n", KEEP),
    ("注释关闭行再开启",    "%%\n第一条结束 %% 正文 %% 第二条开始\n甲\n\n乙\n\n%%\n", KEEP),
    ("非法反引号信息串",    "``` bad`info\n```\n甲\n\n乙\n\n丙\n```\n", KEEP),
    ("类似原始标签名 script", "<script-x>\n\n```\n</script>\n甲\n\n乙\n\n丙\n```\n", KEEP),
    ("类似原始标签名 pre",   "<pre-x>\n\n```\n</pre>\n甲\n\n乙\n\n丙\n```\n", KEEP),
    ("类似原始标签名 style", "<style-x>\n\n```\n</style>\n甲\n\n乙\n\n丙\n```\n", KEEP),
    ("类似原始标签名 textarea", "<textarea-x>\n\n```\n</textarea>\n甲\n\n乙\n\n丙\n```\n", KEEP),
    ("残缺标签吞围栏",      "<widget\n```\n\n甲\n\n乙\n\n```\n", KEEP),
    ("ATX 后接不间断空格",  "#\u00a0*甲\n\n乙*\n", KEEP),
    ("ATX 后接全角空格",    "#\u3000*甲\n\n乙*\n", KEEP),
    ("行内 HTML 吞围栏",    "<span>前言</span>\n```\n\n甲\n\n乙\n\n```\n", KEEP),
    ("块级标签仍开启块",    "<div>\n内部\n\n*外部*\n", KEEP),
    ("引号未闭合的标签",    '<span title="未闭合>\n```\n\n甲\n\n乙\n```\n', KEEP),
    ("带属性的整行标签",    '<span title="x">\n内部\n\n*外部*\n', KEEP),
    ("标签内不间断空格",    '<span\u00a0title="x">\n```\n\n甲\n\n乙\n```\n', KEEP),
    ("标签内全角空格",      '<span\u3000title="x">\n```\n\n甲\n\n乙\n```\n', KEEP),
    ("井号后仅不间断空格",  "#\u00a0\n\n*甲\n", KEEP),
    ("井号后仅全角空格",    "#\u3000\n\n*甲\n", KEEP),
    ("仅含不间断空格的行",  "甲\n\u00a0\n乙\n", KEEP),
    ("仅含全角空格的行",    "甲\n\u3000\n乙\n", KEEP),
    ("安全与禁止混排",      "## 标题\n\n正文一。\n\n正文二。\n\n---\n\n正文三。\n",
                          D(1, 3)),
]


def main():
    bad = 0
    for name, src, expect in CASES:
        drop, held, runs = analyze(src.split("\n"))
        ok = drop == set(expect)
        bad += 0 if ok else 1
        print("%s %-20s 应删 %-8s 实删 %s" % ("✓" if ok else "✗", name,
              sorted(expect) or "无", sorted(drop) or "无"))
    src = "## 标题\n\n一。\n\n二。\n\n---\n\n三。\n"
    lines = src.split("\n")
    drop, _, _ = analyze(lines)
    once = [l for i, l in enumerate(lines) if i not in drop]
    again, _, _ = analyze(once)
    ok = not again
    bad += 0 if ok else 1
    print("%s %-20s" % ("✓" if ok else "✗", "幂等性"))
    print("\n全部通过" if not bad else "\n%d 项未通过" % bad)
    sys.exit(0 if not bad else 1)

if __name__ == "__main__":
    main()
