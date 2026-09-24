#!/usr/bin/env python3
"""报告格式与文风风险检查。

格式项包括加粗闭合、表图编号、标点和单位；文风项包括写作旁白、
指教读者、认知反转、揭晓式表达和段落负担。文风命中只提示人工
复核，不自动改写，也不代表命中句一定错误。研究方法和口径说明
不属于应当机械删除的过程痕迹。

用法：python3 check.py <报告.md> [--fix] [--target obsidian|markdown]
--fix 只自动修复加粗标点位置，其余问题需人工处理。
--target 声明交付目标，影响空行一项的判定：
  obsidian  可删空行计入格式问题，需先用 tidy_blank_lines.py 处理
  markdown  段落间空行应当保留，空行提示不适用
  不传      维持原行为，空行只作提示，不影响是否通过
退出码：0 通过，2 存在需修复的格式问题，1 用法或参数错误。
"""
import io
import os
import re
import shutil
import stat
import sys
import tempfile

PUNCT = "。，；：、！？"
DQ = chr(34)

# 写作旁白与元叙述。只提示表达方式，不包含重新计算、口径调整等研究方法。
TRACE_WORDS = [
    "如前所述", "上一节提到", "下面来看", "接下来我们", "回到前文",
]

# 与最终研究状态无关的版本和写作记录。必要的修订说明由人工判断。
VERSION_WORDS = [
    "上一版", "本版", "原报告", "草稿", "初稿", "本次修改",
    "经过反复讨论后",
]

# 指教读者的句式
PREACH_WORDS = [
    "先问", "必须问清", "第一件事", "想清楚", "读者会犯", "值得深究",
    "读者应", "投资者应", "需要牢记", "切记", "要理解",
    "必须理解", "需要认识到", "不要被",
]

# 演讲修辞
RHETORIC_WORDS = ["顺带说", "潜台词", "一句话概括",
                  "硬币的两面", "一体两面", "压低分子", "放大分母",
                  "常被低估", "往往被忽视", "鲜有人", "值得玩味", "耐人寻味",
                  "洞见在于", "颠覆认知"]

# 这些模式可能有合理用途，只作为风险提示。限制单句跨度，避免跨段误配。
STYLE_PATTERNS = [
    ("二元反转", re.compile(
        r"(?:不是|并非|不由)(?:[^。！？\n]|\n(?!\n)){1,80}(?:而是|却是)")),
    ("表象揭示", re.compile(
        r"(?:看似|表面上?)(?:[^。！？\n]|\n(?!\n)){1,80}(?:实际(?:上)?|本质上|背后)")),
    ("唯一答案", re.compile(
        r"(?:真正(?:的)?(?:决定|关键|分野|问题|约束|答案)|"
        r"核心并不在|本质上|归根结底|说到底|"
        r"更深层(?:的)?(?:问题|逻辑|原因|含义))")),
    ("条件式教导", re.compile(
        r"只有(?:[^。！？\n]|\n(?!\n)){1,60}才能(?:理解|看清|明白|认识)")),
    ("预设误判", re.compile(
        r"(?:如果|若)(?:只|仅)(?:[^。！？\n]|\n(?!\n)){1,70}(?:就会|容易)(?:误判|误解|忽略)|"
        r"不(?:先|加以)?分清(?:[^。！？\n]|\n(?!\n)){1,60}(?:会|就会)(?:犯错|误判|混淆)")),
    ("揭晓推进", re.compile(
        r"(?:这就解释了|这揭示了|(?<!的)答案(?:就在于|是)|谜底在于)")),
    ("过强断言", re.compile(
        r"(?:(?<!非)显然|毫无疑问|显而易见|必然意味着|彻底证明)")),
]


def load(path):
    return io.open(path, encoding="utf-8", newline="").read()


def write_fixed(path, text):
    """保留一份原文件备份，再以原子替换方式写回修复结果。"""
    backup = path + ".bak"
    suffix = 1
    while os.path.exists(backup):
        backup = "%s.bak.%d" % (path, suffix)
        suffix += 1
    shutil.copy2(path, backup)

    directory = os.path.dirname(os.path.abspath(path))
    original_mode = stat.S_IMODE(os.stat(path).st_mode)
    fd, temporary = tempfile.mkstemp(prefix=".report-writer-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.chmod(temporary, original_mode)
        os.replace(temporary, path)
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return backup


def blank_like(text):
    """用空格遮蔽内容，同时保留换行和字符位置。"""
    return "".join("\n" if c == "\n" else "\r" if c == "\r" else " " for c in text)


def mask_inline_code(line):
    """按相同长度的反引号运行配对行内代码；支持跨行，保持字符位置。"""
    chars = list(line)
    runs = list(re.finditer(r"`+", line))
    pos = 0
    while pos < len(runs):
        opening = runs[pos]
        width = opening.end() - opening.start()
        closing = next((i for i in range(pos + 1, len(runs))
                        if runs[i].end() - runs[i].start() == width), None)
        if closing is None:
            pos += 1
            continue
        end = runs[closing].end()
        for idx in range(opening.start(), end):
            if chars[idx] not in "\r\n":
                chars[idx] = " "
        pos = closing + 1
    return "".join(chars)


def mask_inline_images(text):
    """遮蔽行内图片的替代文本和目标，避免把资源描述当作正文修复。"""
    chars = list(text)
    pos = 0
    while True:
        start = text.find("![", pos)
        if start < 0:
            break
        close = start + 2
        while close < len(text):
            if text[close] == "]" and (close == 0 or text[close - 1] != "\\"):
                break
            close += 1
        if close >= len(text):
            break
        end = close + 1
        if end < len(text) and text[end] in "([":
            opening = text[end]
            closing = ")" if opening == "(" else "]"
            depth, idx = 1, end + 1
            while idx < len(text) and depth:
                if text[idx] == "\\":
                    idx += 2
                    continue
                if text[idx] == opening:
                    depth += 1
                elif text[idx] == closing:
                    depth -= 1
                idx += 1
            if depth == 0:
                end = idx
        for idx in range(start, end):
            if chars[idx] not in "\r\n":
                chars[idx] = " "
        pos = end
    return "".join(chars)


def mask_html(text):
    """遮蔽 HTML 注释与标签；标签属性不是报告正文。"""
    chars = list(text)

    def hide(start, end):
        for idx in range(start, end):
            if chars[idx] not in "\r\n":
                chars[idx] = " "

    pos = 0
    while True:
        start = text.find("<!--", pos)
        if start < 0:
            break
        close = text.find("-->", start + 4)
        end = len(text) if close < 0 else close + 3
        hide(start, end)
        pos = end

    pos = 0
    while pos < len(text):
        start = text.find("<", pos)
        if start < 0:
            break
        if start + 1 >= len(text) or not re.match(r"[A-Za-z/!?]", text[start + 1]):
            pos = start + 1
            continue
        idx, quote = start + 1, None
        while idx < len(text):
            char = text[idx]
            if quote:
                if char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == ">":
                hide(start, idx + 1)
                idx += 1
                break
            idx += 1
        pos = idx
    return "".join(chars)


def mask_inline_nonprose(text):
    """统一遮蔽可跨行的行内代码、图片和 HTML。"""
    return mask_html(mask_inline_images(mask_inline_code(text)))


def opening_fence(line):
    """返回 CommonMark 围栏的字符和长度；只接受至多三个前导空格。"""
    body = line.rstrip("\r\n")
    match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", body)
    if not match:
        return None
    marker, info = match.groups()
    if marker[0] == "`" and "`" in info:
        return None
    return marker[0], len(marker)


def closing_fence(line, fence_char, fence_width):
    """闭合围栏必须同字符，且长度不少于起始围栏。"""
    body = line.rstrip("\r\n")
    match = re.match(r"^ {0,3}([`~]+)[ \t]*$", body)
    if not match:
        return False
    marker = match.group(1)
    return marker[0] == fence_char and len(marker) >= fence_width and len(set(marker)) == 1


def starts_with_frontmatter(text):
    """识别文件首行的 YAML frontmatter，允许 UTF-8 BOM。"""
    first = text.splitlines()[0] if text.splitlines() else ""
    return first.lstrip("\ufeff") == "---"


def mask_code_and_metadata(text):
    """遮蔽围栏代码、行内代码和文首 YAML，保留行号与字符位置。"""
    out = []
    in_code = False
    fence = None
    in_yaml = starts_with_frontmatter(text)
    for idx, line in enumerate(text.splitlines(keepends=True)):
        stripped = line.lstrip()
        if in_yaml:
            out.append(blank_like(line))
            if idx and stripped.rstrip("\r\n") in ("---", "..."):
                in_yaml = False
            continue
        if in_code and closing_fence(line, *fence):
            in_code, fence = False, None
            out.append(blank_like(line))
            continue
        if in_code:
            out.append(blank_like(line))
        elif opening_fence(line):
            in_code, fence = True, opening_fence(line)
            out.append(blank_like(line))
        elif line.startswith("    ") or line.startswith("\t"):
            out.append(blank_like(line))
        else:
            out.append(line)
    return mask_inline_nonprose("".join(out))


def check_bold(text):
    """加粗闭合与标点位置。返回 (问题列表, 修复后文本)"""
    problems, fixed = [], 0
    scan = mask_nonprose(text)
    pos = [m.start() for m in re.finditer(r"\*\*", scan)]
    if len(pos) % 2:
        ln = scan[:pos[-1]].count("\n") + 1 if pos else 1
        line = text.splitlines()[ln - 1] if text.splitlines() else ""
        problems.append((ln, "加粗标记数为奇数", line[:40]))
        return problems, text, fixed

    replacements = []
    for a, b in zip(pos[0::2], pos[1::2]):
        content = text[a + 2:b]
        ln = text[:a].count("\n") + 1
        if not content.strip():
            problems.append((ln, "空加粗", content[:24]))
        elif content[0] in PUNCT + " ":
            problems.append((ln, "内容以标点或空格开头，可能配对错乱", content[:24]))
        else:
            after = text[b + 2:b + 3]
            if content[-1] in PUNCT and after and after not in PUNCT and not after.isspace():
                problems.append((ln, "标点在加粗内且后接文字，无法闭合", content[-14:]))
                replacements.append((a, b, content))

    fixed_text = text
    for a, b, content in reversed(replacements):
        fixed_text = fixed_text[:a + 2] + content[:-1] + "**" + content[-1] + fixed_text[b + 2:]
        fixed += 1
    return problems, fixed_text, fixed


def mask_nonprose(text):
    """遮蔽代码块、表格、图片和块引用，保持字符位置与行号不变。"""
    out = []
    in_code = False
    fence = None
    in_callout = False
    in_yaml = starts_with_frontmatter(text)
    for idx, line in enumerate(text.splitlines(keepends=True)):
        stripped = line.lstrip()
        if in_yaml:
            out.append(blank_like(line))
            if idx and stripped.rstrip("\r\n") in ("---", "..."):
                in_yaml = False
            continue
        if in_code and closing_fence(line, *fence):
            in_code, fence = False, None
            out.append(blank_like(line))
            continue
        if not in_code and opening_fence(line):
            in_code, fence = True, opening_fence(line)
            out.append(blank_like(line))
            continue
        if stripped.startswith("> [!"):
            in_callout = True
        elif not stripped.startswith(">"):
            in_callout = False
        if (in_code or line.startswith("    ") or line.startswith("\t")
                or (stripped.startswith(">") and not in_callout)
                or stripped.startswith(("|", "!["))
                or re.match(r"^ {0,3}(?:\*[ \t]*){3,}\r?\n?$", line)):
            out.append(blank_like(line))
        else:
            out.append(line)
    return mask_inline_nonprose("".join(out))


def check_traces(text):
    """写作旁白：正文从严提示，版本记录全文提示。"""
    m = re.search(r"^## 附录", text, re.M)
    body = text[:m.start()] if m else text
    scan = mask_nonprose(body)
    hits = []
    for group, words in (("写作旁白", TRACE_WORDS), ("指教读者", PREACH_WORDS), ("演讲修辞", RHETORIC_WORDS)):
        for w in words:
            for mt in re.finditer(re.escape(w), scan):
                ln = scan[:mt.start()].count("\n") + 1
                ctx = body[max(0, mt.start() - 30):mt.start() + 40].replace("\n", "")
                hits.append((ln, group, w, ctx))
    full_scan = mask_nonprose(text)
    for w in VERSION_WORDS:
        for mt in re.finditer(re.escape(w), full_scan):
            ln = full_scan[:mt.start()].count("\n") + 1
            ctx = text[max(0, mt.start() - 30):mt.start() + 40].replace("\n", "")
            hits.append((ln, "版本对照", w, ctx))
    return sorted(hits)


def body_before_appendix(text):
    """返回正文；附录中的口径说明不参加文风密度统计。"""
    m = re.search(r"^## 附录", text, re.M)
    return text[:m.start()] if m else text


def check_style_patterns(text):
    """检查需要人工判断的语义句式，并给出上下文。"""
    body = body_before_appendix(text)
    scan = mask_nonprose(body)
    hits = []
    for group, pattern in STYLE_PATTERNS:
        for mt in pattern.finditer(scan):
            ln = scan[:mt.start()].count("\n") + 1
            ctx = body[max(0, mt.start() - 35):mt.end() + 45].replace("\n", "")
            hits.append((ln, group, mt.group(0), ctx))

    # 一次出现可能是必要定义；集中出现时提示整体语气风险。
    prose_chars = len(re.sub(r"[\s|#*`>\-]", "", scan))
    if hits and prose_chars:
        per_10k = len(hits) * 10000.0 / prose_chars
        if len(hits) >= 3 and per_10k >= 2.0:
            hits.append((0, "修辞密度", "%d 处" % len(hits),
                         "每万字约 %.1f 处，建议集中复核摘要、章节首尾与结论" % per_10k))
    return sorted(hits)


def check_readability(text):
    """检查段落级阅读负担；只提示，不作自动判断。"""
    body = body_before_appendix(text)
    notes = []
    in_code = False
    block, start_ln = [], None

    def assess(parts, ln):
        if not parts:
            return
        plain = " ".join(parts)
        plain = re.sub(r"\[[^\]]+\]\([^)]*\)", "", plain)
        plain = re.sub(r"[*_`]", "", plain)
        if len(plain) >= 350:
            notes.append((ln, "长段落", len(plain), plain[:70]))

        sentences = [s for s in re.split(r"[。！？]", plain) if s.strip()]
        longest = max((len(s) for s in sentences), default=0)
        if longest >= 160:
            notes.append((ln, "长句", longest, plain[:70]))

        parens = len(re.findall(r"[（(]", plain))
        if parens >= 4:
            notes.append((ln, "括号密集", parens, plain[:70]))

    def flush():
        nonlocal block, start_ln
        assess(block, start_ln)
        block, start_ln = [], None

    for ln, line in enumerate(body.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            flush()
            in_code = not in_code
            continue
        if (in_code or line.startswith("    ") or line.startswith("\t")
                or not stripped or stripped.startswith(("#", "|", "![", ">"))):
            flush()
            continue
        if re.match(r"^(?:[-*+] |\d+[.)] )", stripped):
            flush()
            assess([stripped], ln)
            continue
        if start_ln is None:
            start_ln = ln
        block.append(stripped)
    flush()
    return notes


def check_numbering(text, kind):
    """表/图编号连续性与引用完整性。"""
    title_pattern = re.compile(r"^\s*\*\*%s\s*(\d+)[　 \t:：]" % kind)
    ref_pattern = re.compile(r"%s\s*(\d+)(?!\d)" % kind)
    titles, refs = [], set()
    for line in mask_code_and_metadata(text).splitlines():
        title = title_pattern.match(line)
        if title:
            titles.append(int(title.group(1)))
            continue
        if line.lstrip().startswith("!["):
            continue
        refs.update(int(m.group(1)) for m in ref_pattern.finditer(line))
    problems = []
    if not titles:
        return problems
    if titles != list(range(1, len(titles) + 1)):
        problems.append("%s编号不连续或重复：%s" % (kind, titles))
    unref = [t for t in titles if t not in refs]
    if unref:
        problems.append("%s未被正文引用：%s" % (kind, unref))
    return problems


def check_misc(text):
    """较确定的正文格式问题；只保留适合阻断交付的项目。"""
    problems = []
    scan = mask_nonprose(text)
    if scan.count(DQ) % 2:
        problems.append("双引号数量为奇数，存在未配对")
    ascii_punct_lines = sorted({
        scan[:m.start()].count("\n") + 1
        for m in re.finditer(r"(?<=[\u4e00-\u9fff%）\d])[,;:](?=[\u4e00-\u9fff])", scan)
    })
    if ascii_punct_lines:
        problems.append("中文正文夹用半角逗号、分号或冒号：行 %s" % ascii_punct_lines)
    return problems


def check_blank_lines(text):
    """空行提示：Obsidian 正文段落之间不留空行，标题下方不留空行。
    判定逻辑在 blank_lines.py，与 tidy_blank_lines.py 共用同一份实现；
    反例测试集见 tests_blank_lines.py。"""
    from blank_lines import analyze
    drop, held, runs = analyze(text.split("\n"))

    def brief(xs):
        xs = sorted(x + 1 for x in xs)
        return ", ".join(str(x) for x in xs[:8]) + ("…" if len(xs) > 8 else "")

    notes = []
    if drop:
        notes.append("可删空行 %d 处：行 %s；Obsidian 正文段落之间直接换行即可，"
                     "标题正下方不留空行。交付到按标准 Markdown 解析的场合才保留"
                     % (len(drop), brief(drop)))
    if runs:
        notes.append("连续多个空行 %d 处：行 %s；需人工确认，不做批量压缩"
                     % (len(runs), brief(runs)))
    for i, why in held[:5]:
        notes.append("行 %d 的空行保留：%s" % (i + 1, why))
    return notes


def blank_drop_count(text):
    """可删空行的数量，供交付目标判定使用；判定逻辑与 check_blank_lines 同源。"""
    from blank_lines import analyze
    drop, _held, _runs = analyze(text.split("\n"))
    return len(drop)


def check_contextual(text):
    """依赖交付场景或语义的提示，不影响检查是否通过。"""
    notes = []
    scan = mask_code_and_metadata(text)
    if text.startswith("---\n") or text.startswith("---\r\n"):
        notes.append("含 YAML frontmatter；仅在用户或交付模板需要时保留，写入 Obsidian 正文通常删除")

    for unit in ["平方呎", "平方英尺", "英里", "磅", "加仑", "华氏"]:
        n = scan.count(unit)
        if n and not re.search(r"1 ?%s ?(?:[＝=]|约等于|相当于)" % unit, scan):
            notes.append("英制单位「%s」出现 %d 次；按用户、来源引用和交付场景判断是否换算" % (unit, n))

    dash = [i for i, line in enumerate(scan.split("\n"), 1)
            if line.count("\u2014\u2014") >= 2 and not line.startswith("|")]
    if dash:
        notes.append("同一行出现两对破折号，建议复核主干是否被切断：行 %s" % dash)

    for code in [r"\bL[0-9]\b", r"Tier ?[0-9]", r"方案 ?[A-D]\b"]:
        if re.search(code, scan):
            notes.append("出现可能需要解释的代号：%s；用户模板或正式名称可保留" % code)

    # 只统计行内强调加粗：排除表格行、表图题、以加粗开头的段落标签
    inline = 0
    prose_char = 0
    for l in scan.split("\n"):
        if l.startswith("|") or re.match(r"\*\*[表图] \d+", l):
            continue
        prose_char += len(l)
        body = re.sub(r"^\s*(?:[-*]\s*)?\*\*[^*\n]+\*\*", "", l)  # 去掉行首段落标签
        inline += len(re.findall(r"\*\*[^*\n]+\*\*", body))
    if prose_char > 8000 and inline > prose_char / 1200:
        notes.append(
            "行内强调加粗 %d 处 / 正文 %d 字符，密度偏高（段落标签不计；建议每 1200 字符不超过 1 处）"
            % (inline, prose_char))
    return notes


def check_hierarchy(text):
    """层次密度、并列项呈现、表格密集。返回提示列表（需人工判断）。"""
    lines = mask_code_and_metadata(text).split("\n")
    heads = [(i, len(m.group(1)), m.group(2).strip())
             for i, l in enumerate(lines)
             for m in [re.match(r"^(#{1,6}) (.+)", l)] if m]
    if not heads:
        return []
    out = []

    for (ln1, lv1, _), (ln2, lv2, name2) in zip(heads, heads[1:]):
        if lv2 > lv1 + 1:
            out.append("行%-5d %s：标题由 H%d 跳到 H%d，建议检查层级"
                       % (ln2 + 1, name2[:20], lv1, lv2))

    def body_of(k):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        return lines[heads[k][0] + 1:end]

    def scope_end(k):
        lv = heads[k][1]
        for j in range(k + 1, len(heads)):
            if heads[j][1] <= lv:
                return heads[j][0]
        return len(lines)

    def tags_of(k):
        return set(re.findall(r"^\*\*([^*\n]{2,20})\*\*",
                              "\n".join(body_of(k)), re.M))

    def paragraphs(parts):
        """按空行而不是软换行识别正文段落。"""
        outp, block = [], []
        for line in parts:
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "|", "![", ">", "```", "~~~")):
                if block:
                    outp.append(" ".join(block))
                    block = []
                continue
            block.append(stripped)
        if block:
            outp.append(" ".join(block))
        return outp

    # 附录内的小节整体豁免并列编号要求
    apx = [h[0] for h in heads if h[1] == 2 and h[2].startswith("附录")]
    apx_from = min(apx) if apx else len(lines)

    for k, (ln, lv, name) in enumerate(heads):
        paras = paragraphs(body_of(k))
        if lv == 3 and len(paras) >= 12:
            if not any(heads[j][1] == 4 for j in range(k + 1, len(heads))
                       if heads[j][0] < scope_end(k)):
                out.append("行%-5d %s：直属正文 %d 段且无四级子节，建议内部分层"
                           % (ln + 1, name[:20], len(paras)))
        if ln >= apx_from:
            continue
        bold = [x for x in paras if re.match(r"^\*\*[^*\n]{2,20}\*\*", x)]
        if len(bold) < 5:
            continue
        if any(re.match(r"^\*\*[一二三四五六七八九十]+、", x) for x in bold):
            continue
        # 同级兄弟节共用同一套标签时属画像式结构，结构重复本身建立预期
        mine, shared = tags_of(k), False
        for j, (ln2, lv2, _) in enumerate(heads):
            if j != k and lv2 == lv and len(mine & tags_of(j)) >= 3:
                shared = True
                break
        if not shared:
            out.append("行%-5d %s：%d 个并列加粗段，建议按内容改用编号、项目符号或表格"
                       % (ln + 1, name[:20], len(bold)))

    # 四级子节体量失衡：按作用域总量计，避免误判"内容都在更深层级"的小节
    for k, (ln, lv, name) in enumerate(heads):
        if lv != 3:
            continue
        kids = [j for j in range(k + 1, len(heads))
                if heads[j][1] == 4 and heads[j][0] < scope_end(k)]
        if len(kids) < 2:
            continue
        sizes = [len(paragraphs(lines[heads[j][0] + 1:scope_end(j)])) for j in kids]
        if max(sizes) >= 8 * max(1, min(sizes)):
            out.append("行%-5d %s：四级子节体量 %s，相差一个量级，建议检查是否过度拆分或需要再分层"
                       % (ln + 1, name[:20], sizes))

    # 连续表格：相邻两表之间正文少于三段视为紧邻，连续四张则提示
    tpos = [i for i, l in enumerate(lines) if re.match(r"^\*\*表\s*\d+", l)]
    run = []
    for a, b in zip(tpos, tpos[1:]):
        if any(line.startswith("#") for line in lines[a + 1:b]):
            if len(run) >= 4:
                out.append("行%-5d 连续 %d 张表之间缺少承转说明，建议拆到不同小节"
                           % (run[0] + 1, len(run)))
            run = []
            continue
        gap = len([x for x in lines[a:b]
                   if x.strip() and not x.startswith("|")
                   and not re.match(r"^\*\*表\s*\d+", x) and not x.startswith("#")])
        if gap < 3:
            run = run or [a]
            run.append(b)
        else:
            if len(run) >= 4:
                out.append("行%-5d 连续 %d 张表之间缺少承转说明，建议拆到不同小节"
                           % (run[0] + 1, len(run)))
            run = []
    if len(run) >= 4:
        out.append("行%-5d 连续 %d 张表之间缺少承转说明，建议拆到不同小节"
                   % (run[0] + 1, len(run)))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    do_fix = "--fix" in sys.argv
    target, seen, i = None, 0, 2
    options = sys.argv[2:]
    while i - 2 < len(options):
        arg = options[i - 2]
        if arg == "--target":
            following = options[i - 1] if i - 1 < len(options) else None
            if following is None or following.startswith("-"):
                print("--target 缺少取值，应为 obsidian 或 markdown")
                sys.exit(1)
            target, seen, i = following, seen + 1, i + 2
            continue
        if arg.startswith("--target="):
            target, seen = arg.split("=", 1)[1], seen + 1
        elif arg != "--fix":
            print("未知参数：%s" % arg)
            sys.exit(1)
        i += 1
    if seen > 1:
        print("--target 重复声明")
        sys.exit(1)
    if target not in (None, "obsidian", "markdown"):
        print("--target 仅支持 obsidian 或 markdown")
        sys.exit(1)
    text = load(path)

    bold_problems, fixed_text, n_fixed = check_bold(text)
    if do_fix and n_fixed:
        backup = write_fixed(path, fixed_text)
        print("已自动修复加粗标点位置 %d 处；原文件备份：%s\n" % (n_fixed, backup))
        bold_problems = [p for p in bold_problems if "无法闭合" not in p[1]]
        text = fixed_text

    ok = True

    print("── 加粗 ──")
    if bold_problems:
        ok = False
        for ln, kind, ctx in bold_problems:
            print("  行%-5s %s：%s" % (ln, kind, ctx))
    else:
        print("  正常")

    print("\n── 编号与引用（需结合全文或模板判断）──")
    numbering = check_numbering(text, "表") + check_numbering(text, "图")
    num_problems = [x for x in numbering if "不连续" in x]
    num_notes = [x for x in numbering if "未被正文引用" in x]
    if num_problems:
        for p in num_problems:
            print("  提示：" + p + "；局部更新、历史编号或用户模板可不从 1 连续")
    if num_notes:
        for p in num_notes:
            print("  提示：" + p + "；若表图紧邻说明或模板不要求显式引用，可保留")
    if not num_problems and not num_notes:
        print("  正常")

    print("\n── 其他格式 ──")
    misc = check_misc(text)
    if misc:
        ok = False
        for p in misc:
            print("  " + p)
    else:
        print("  正常")

    print("\n── 交付场景（需人工判断）──")
    contextual = check_contextual(text)
    if contextual:
        for p in contextual:
            print("  " + p)
    else:
        print("  未发现依赖交付场景的格式项")

    print("\n── 空行（Obsidian 正文）──")
    blanks = check_blank_lines(text)
    if blanks:
        for p_ in blanks:
            print("  " + p_)
    else:
        print("  正常")
    if target == "markdown":
        print("  目标为 markdown：段落之间应保留空行，上列可删提示不适用")
    elif target == "obsidian" and blank_drop_count(text):
        ok = False
        print("  目标为 obsidian：可删空行须先处理，运行 tidy_blank_lines.py <文件> 查看 diff，确认后加 --apply")

    print("\n── 层次（需人工判断）──")
    hier = check_hierarchy(text)
    if hier:
        for x in hier:
            print("  " + x)
    else:
        print("  未发现层次失衡")

    print("\n── 文体与版本痕迹（需人工判断是否误报）──")
    traces = check_traces(text)
    if traces:
        for ln, group, w, ctx in traces:
            loc = "行%-5s" % ln if ln else "全文  "
            print("  %s [%s] %s ｜ …%s…" % (loc, group, w, ctx))
    else:
        print("  未发现写作旁白、指教句式与演讲修辞")

    print("\n── 平视表达风险（命中不等于错误）──")
    style_hits = check_style_patterns(text)
    if style_hits:
        for ln, group, phrase, ctx in style_hits:
            loc = "行%-5s" % ln if ln else "全文  "
            print("  %s [%s] %s ｜ …%s…" % (loc, group, phrase, ctx))
    else:
        print("  未发现集中使用的反转、揭晓或过强断言句式")

    print("\n── 段落负担（需人工判断）──")
    readability = check_readability(text)
    if readability:
        for ln, group, value, ctx in readability:
            unit = "字" if group in ("长段落", "长句") else "组括号"
            print("  行%-5s [%s] %s%s ｜ %s…" % (ln, group, value, unit, ctx))
    else:
        print("  未发现特别长的段落、句子或括号密集行")

    if ok:
        print("\n格式检查通过；文风仍需按风险提示和 SKILL.md 清单人工复核")
    else:
        print("\n存在需修复的格式问题；文风仍需人工复核")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
