# -*- coding: utf-8 -*-
"""Obsidian 正文空行判定：找出可以安全删除的空行。

这不是「保持解析结果不变」的清理，也不对任意 Markdown 文档提供解析等价保证。

预期的变换只有两种：合并已识别的顶层普通段落，删除已识别的 ATX 标题下方的
单个空行。对已识别的代码、HTML、注释、公式等受保护结构，不产生内部删除候选；
对不支持或归属不确定的语法保守跳过。第三方插件语法不在保证范围内。
应用前必须看 diff，复杂文档还要核对 Obsidian 的渲染结果。

策略是限定安全子集，不是逐行猜测：
- 只有顶层、无缩进、不含任何可能打断段落的行、且通过行内白名单的普通段落，
  才是合并候选；
- 边界无法确定的结构整块保护，内部空行一律不动；
- 连续空行不做兜底压缩，只报告。
宁可漏删。

适用范围与残余风险：

- 这是候选空行筛选器，不是完整的 Markdown / Obsidian 解析器。测试通过、重复
  运行结果稳定，不代表对任意输入都具有解析等价保证。
- 预期语料是以中文普通段落、常规表格、列表、图片嵌入和水平分隔线为主的研究
  报告。第三方插件语法、残缺语法、复杂嵌套结构不在保证范围内。
- 合并普通段落会有意改变段落边界，可能影响阅读节奏、段落间距和其他以段落为
  单位的展示行为。纯文本且语法安全，不等于语义上适合合并，需由人工判断。
- 表格、列表、引用、链接引用定义及其续行采用保守规则识别，不是完整的容器解析。
  复杂缩进、嵌套、惰性续行和非标准写法需要额外检查。
- HTML 块的识别覆盖块级标签白名单与整行单标签两类，属性语法按 CommonMark 校验，
  但不保证与解析器完全一致；残缺或异常标签不在保证范围内。
- 无法识别或归属不确定的内容会导致漏删，保守保护还可能扩大到后续正文。不应
  因为候选少或没有候选，就推断文档结构已被正确识别。
- 每次应用前必须审核完整 diff，确认每一处段落合并和标题后空行删除都符合意图；
  结构复杂或显示效果不确定时，还要核对 Obsidian 的渲染结果。
- 应保留原文件或版本记录以便回退。生成 diff 后源文件若有变化，必须重新分析，
  不能直接套用旧候选。

历史反例（都曾出过问题或被复审指出），对应 tests_blank_lines.py：
- `---` 紧跟正文是 setext 下划线，会把上一段变成标题；下划线不限三个字符，
  `-`、`--`、`=` 同样成立，而 `***`、`___` 是合法分隔线；
- 普通段落区间里可能混进围栏、引用、列表、下划线，只看第一行会把它们吞掉；
- GFM 表格的数据行可以不以 `|` 开头；
- 列表与引用的续行不带标记，看起来就是普通正文；
- 围栏关闭要求同种字符、不短于开栏、缩进不超过三格，缩进更深的是代码内容；
- HTML 原始块必须用对应的结束标签关闭，`<script>` 里的 `</style>` 不算；
- 段落合并后行内标记重新配对：`*alpha` 与 `beta*`、`_alpha` 与 `beta_`、
  跨段的 `[文字` `](url)`，原本互不相干；
- 转义和代码跨度会让「计数成偶数」失真，所以含反斜杠或反引号一律不合并。
"""
import re
import unicodedata

SETEXT = re.compile(r"^(=+|-+)\s*$")
THEMATIC = re.compile(r"^(\*{3,}|_{3,}|-{3,})\s*$")
# 只接受 ASCII 空格或 Tab：`\s` 会把不间断空格、全角空格也当成标题分隔符，
# 于是普通段落被提升为标题，走标题分支绕过行内白名单。
ATX = re.compile(r"^#{1,6}(?=[ \t]|$)")
LIST = re.compile(r"^([-*+](\s|$)|\d+[.)](\s|$))")
TABLE_DELIM = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")
FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")   # 只认空格：Tab 已到第 4 列
# 标签名后必须是空白、`>` 或行尾：`\b` 是正则的单词边界，不是标签名边界，
# 会把 <script-x> 误认成 <script> 原始块，进而吞掉真正的围栏开启行。
HTML_RAW = re.compile(r"^ {0,3}<(script|pre|style|textarea)(?=[ \t]|>|$)", re.I)
HTML_COMMENT = re.compile(r"^ {0,3}<!--")
# 开启 HTML 块分两种：块级标签（CommonMark 第 6 类），或整行只有一个完整标签
#（第 7 类）。`<widget` 这种残缺形式、`<span>前言</span>` 这种行内 HTML 都是普通
# 正文，按 HTML 块处理会把下一行真正的围栏开栏一并吞掉。
HTML_BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|"
    "colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|"
    "form|frame|frameset|h1|h2|h3|h4|h5|h6|head|header|hr|html|iframe|legend|li|"
    "link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|"
    "section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul"
)
HTML_BLOCK = re.compile(r"^ {0,3}</?(%s)(?=[ \t/>]|$)" % HTML_BLOCK_TAGS, re.I)
# 第 7 类要求整行只有一个完整标签。属性要按语法校验，引号必须闭合：
# `<span title="未闭合>` 不是完整标签，误判会把下一行的围栏开栏一并吞掉。
# 标签内部的空白只认空格与 Tab：Python 的 `\s` 还会接受不间断空格、全角空格，
# 它们不是 CommonMark 的标签分隔符，误判同样会吞掉后续的围栏开栏。
_WS = r"[ \t]"
_ATTR = (r"(?:%s+[a-zA-Z_:][a-zA-Z0-9_.:-]*"
         r"(?:%s*=%s*(?:[^ \t\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*" % (_WS, _WS, _WS))
HTML_SOLO = re.compile(r"^ {0,3}(?:<[a-zA-Z][a-zA-Z0-9-]*%s%s*/?>"
                       r"|</[a-zA-Z][a-zA-Z0-9-]*%s*>)[ \t]*$" % (_ATTR, _WS, _WS))
HTML_LOOSE = re.compile(r"^ {0,3}<[a-zA-Z/!?]")   # 仅用于保守拒绝，不用于开启块


def _html_opener(line):
    return bool(HTML_BLOCK.match(line) or HTML_SOLO.match(line))
HTML_PI = re.compile(r"^ {0,3}(<\?|<!\[CDATA\[|<![A-Z])")
LINKDEF = re.compile(r"^ {0,3}\[[^\]]+\]:")

PROTECTED, HEADING, PARA, BLANK = "protected", "heading", "para", "blank"


def _interrupts(line):
    """这一行出现在段落中间时，会不会打断段落或改变上文的解析。"""
    st = line.strip()
    if not st:
        return False
    return bool(
        FENCE.match(line) or SETEXT.match(st) or THEMATIC.match(st)
        or ATX.match(line.lstrip(" \t")) or LIST.match(st) or st.startswith(">")
        or st.startswith("$$") or "%%" in line
        or HTML_LOOSE.match(line) or HTML_PI.match(line)
        or LINKDEF.match(line) or TABLE_DELIM.match(line)
    )


def _blank(line):
    """Markdown 的空行只由空格和 Tab 构成。用 strip() 判断会把仅含不间断空格、
    全角空格的正文行也当成空行删掉，那已经超出「只删空行」的范围。"""
    return not line.strip(" \t")


def _fence_opener(line):
    """合法的围栏开启行。形状匹配不等于合法开栏：反引号围栏的信息串里不能再有反引号，
    否则真正的开栏会被当成关闭行，代码块内部就暴露成了普通段落。"""
    m = FENCE.match(line)
    if not m:
        return None
    if m.group(2)[0] == "`" and "`" in m.group(3):
        return None
    return m


def _persistent_opener(line):
    """开启后要跨空行延续到自己的结束标记的块。任何分支扫到它都必须停下交回控制权。

    `%%` 用「整行包含」判断而不是行首：Obsidian 注释可以从行中间开始，
    只在主循环当前行检查会被区段扫描绕过，注释内部的空行仍会被删。"""
    st = line.strip()
    return bool("%%" in line or _fence_opener(line) or HTML_RAW.match(line)
                or HTML_COMMENT.match(line) or HTML_PI.match(line)
                or st.startswith("$$"))


def _run_end(lines, i):
    """非空行区段的结束位置；中途遇到持续块的开启行就停在那里，交回主循环重新分派。"""
    j = i
    n = len(lines)
    while j < n and not _blank(lines[j]):
        if j > i and _persistent_opener(lines[j]):
            return j, True
        j += 1
    return j, False


def segment(lines):
    """把文档切成带类型的区段，返回与行等长的类型表。"""
    kind = [None] * len(lines)
    n = len(lines)
    i = 0
    if n and lines[0].strip() == "---":                     # YAML frontmatter
        j = 1
        while j < n and lines[j].strip() != "---":
            j += 1
        if j < n:
            for k in range(j + 1):
                kind[k] = PROTECTED
            i = j + 1
    while i < n:
        line = lines[i]
        st = line.strip()
        if _blank(line):
            kind[i] = BLANK
            i += 1
            continue
        if "%%" in line:
            # Obsidian 注释可以从行中间开始，一行里还可以关闭后再次开启
            #（`%% 甲 %% 正文 %%`）。逐行判断闭合状态不可靠，直接从这一行起
            # 整份文件不再产生候选。代价是注释之后的正文也不再清理。
            for k in range(i, n):
                kind[k] = PROTECTED
            break
        m = _fence_opener(line)
        if m:                                               # 围栏代码块
            ch, width = m.group(2)[0], len(m.group(2))
            kind[i] = PROTECTED
            j = i + 1
            while j < n:
                kind[j] = PROTECTED
                m2 = FENCE.match(lines[j])
                if (m2 and m2.group(2)[0] == ch
                        and len(m2.group(2)) >= width
                        and re.match(r"^[ \t]*$", m2.group(3))):   # 尾部只允许空格与 Tab
                    j += 1
                    break
                j += 1
            i = j
            continue
        if re.match(r"^(    |\t)", line):                   # 缩进代码块
            j = i
            while j < n and (re.match(r"^(    |\t)", lines[j]) or _blank(lines[j])):
                kind[j] = PROTECTED
                j += 1
            # 紧跟的无缩进行可能是列表项内段落的惰性续行，归属不确定，一并保护
            if j < n and not _blank(lines[j]) and not _persistent_opener(lines[j]):
                # _run_end 有意不检查首行，这里的首行却可能正是围栏开启行
                j, _ = _run_end(lines, j)
                for k in range(i, j):
                    kind[k] = PROTECTED
            i = j
            continue
        if st.startswith("$$"):                             # 公式块（注释已在上面拦截）
            tok = "$$"
            kind[i] = PROTECTED
            j = i + 1
            if st == tok or len(st) == 2 or not st.endswith(tok):
                while j < n:
                    kind[j] = PROTECTED
                    if tok in lines[j]:
                        j += 1
                        break
                    j += 1
            i = j
            continue
        if HTML_PI.match(line):                              # <? ?>、CDATA、声明
            end = "?>" if st.startswith("<?") else ("]]>" if st.startswith("<![CDATA[") else ">")
            kind[i] = PROTECTED
            j = i + 1
            if end not in st[2:]:
                while j < n:
                    kind[j] = PROTECTED
                    if end in lines[j]:
                        j += 1
                        break
                    j += 1
            i = j
            continue
        if HTML_RAW.match(line) or HTML_COMMENT.match(line) or _html_opener(line):
            # HTML 块：原始块认对应的结束标记，其余到空行为止
            tag = None
            m2 = HTML_RAW.match(line)
            if m2:
                tag = m2.group(1).lower()
            comment = bool(HTML_COMMENT.match(line))
            kind[i] = PROTECTED
            j = i + 1
            closed = bool(
                (tag and re.search(r"</%s>" % tag, line, re.I))
                or (comment and "-->" in line)
            )
            while j < n and not closed:
                if not tag and not comment and _blank(lines[j]):
                    break
                kind[j] = PROTECTED
                if tag and re.search(r"</%s>" % tag, lines[j], re.I):
                    j += 1
                    break
                if comment and "-->" in lines[j]:
                    j += 1
                    break
                j += 1
            i = j
            continue
        if (LINKDEF.match(line) or st.startswith(">") or LIST.match(st)
                or (i + 1 < n and TABLE_DELIM.match(lines[i + 1]))):
            # 链接引用定义、引用、列表、表格：连同续行整块保护。
            # 未缩进的围栏可以结束这些容器并开启顶层代码块，扫到就停下交回，
            # 否则围栏内部的区段会被当成普通段落。
            j, _ = _run_end(lines, i)
            for k in range(i, j):
                kind[k] = PROTECTED
            i = j
            continue
        if THEMATIC.match(st) or SETEXT.match(st):
            kind[i] = PROTECTED
            i += 1
            continue
        if ATX.match(line):     # 用 line 不用 st：strip() 会去掉 NBSP、全角空格
            kind[i] = HEADING
            i += 1
            continue
        # 普通段落：整段都要干净——无缩进，且后续行不含任何可能打断段落的构造。
        # 若中途开启围栏或原始 HTML，必须把控制权交给对应的块处理，让状态延续过空行，
        # 否则围栏内部的两个区段会被当成两个普通段落，中间的空行被删掉。
        j, hit_opener = _run_end(lines, i)
        safe = not hit_opener
        for k in range(i, j):
            if lines[k].startswith((" ", "\t")) or (k > i and _interrupts(lines[k])):
                safe = False
        for k in range(i, j):
            kind[k] = PARA if safe else PROTECTED
        i = j
    return kind


# 行内判定不做「配对校验」。CommonMark 的定界符规则涉及两侧标点、词内限制、
# 定界符串长度消耗，分 token 做栈校验替代不了解析器，已被这些反例推翻：
#   `*a!*b` / `c*!d*`（标点参与 flanking）、`_a_b` / `c_d_`（词内限制）、
#   `***a**` / `**b***`（三连星的剩余定界符）。
# 改为窄白名单：只放行纯文本，外加行首一个 **标签** 这一种固定形式。
# 被拒的字符各有原因：反引号与反斜杠是代码跨度和转义；方括号尖括号是链接与
# 行内 HTML；`|` 是表格（单列表格能把后文吞成数据行）；`^` 是 Obsidian 块 ID
# （合并会改变块引用范围）；`~` `=` `$` 是删除线、高亮、公式；`%%` 是注释。
FORBIDDEN_CHARS = "`\\[]<>~=$|^"
# 行首加粗标签。两端无空白还不够：`**甲！**乙` 的结尾 ** 前是标点、后是文字，
# 按 flanking 规则不能收尾，会留下可跨段配对的余量；而 `**按期间计价。** 正文`
# 的结尾 ** 后面是空格，属于合法收尾。所以按 flanking 规则判，不能只看空白。
LABEL = re.compile(r"^\*\*(?!\s)([^*_\n]*[^*_\s])\*\*")


def _punct(ch):
    return bool(ch) and unicodedata.category(ch)[0] in ("P", "S")


def _label_closes(head, m):
    """标签结尾的 ** 是否构成合法的关闭定界符。"""
    content = m.group(1)
    prev = content[-1]
    nxt = head[m.end():m.end() + 1]
    if prev.isspace():
        return False
    # 前一个字符是标点时，只有后面接空白、标点或行尾才算右侧贴合
    return not _punct(prev) or (not nxt or nxt.isspace() or _punct(nxt))


def mergeable(block):
    """这一段能否参与合并。判不准的一律拒绝，宁可漏删。"""
    text = "\n".join(block)
    if any(ch in text for ch in FORBIDDEN_CHARS) or "%%" in text:
        return False
    head = block[0]
    m = LABEL.match(head)                    # 只允许行首一个完整的加粗标签
    if m and not _label_closes(head, m):
        return False
    rest = (head[m.end():] if m else head) + "\n" + "\n".join(block[1:])
    return "*" not in rest and "_" not in rest


def _para_bounds(lines, idx):
    a = idx
    while a > 0 and not _blank(lines[a - 1]):
        a -= 1
    b = idx
    while b + 1 < len(lines) and not _blank(lines[b + 1]):
        b += 1
    return a, b


def analyze(lines):
    """返回 (可删空行的行号集合, 候选但被拒绝的原因, 连续空行位置)。行号从 0 起。"""
    kind = segment(lines)
    n = len(lines)
    drop, held, runs = set(), [], []
    i = 0
    while i < n:
        if kind[i] != BLANK:
            i += 1
            continue
        j = i
        while j < n and kind[j] == BLANK:
            j += 1
        prev = next((k for k in range(i - 1, -1, -1) if kind[k] != BLANK), None)
        if prev is None or j >= n:
            i = j
            continue
        if j - i > 1:
            runs.append(i)
            i = j
            continue
        if kind[prev] == HEADING and kind[j] in (PARA, HEADING):
            drop.add(i)
        elif kind[prev] == PARA and kind[j] == PARA:
            ua, ub = _para_bounds(lines, prev)
            da, db = _para_bounds(lines, j)
            up, down = lines[ua:ub + 1], lines[da:db + 1]
            if not mergeable(up) or not mergeable(down):
                held.append((i, "行内标记或转义跨段落会重新配对"))
            elif up[-1].endswith("  ") or up[-1].endswith("\\"):
                held.append((i, "上一行是硬换行"))
            else:
                drop.add(i)
        i = j
    return drop, held, runs
