# -*- coding: utf-8 -*-
"""删除 Obsidian 正文中多余的空行（段落之间、标题正下方）。

判定逻辑在 blank_lines.py，与 check.py 共用同一份实现。
注意：删掉段落间的空行会把两个 paragraph 合并成一个，这是有意的结构变换，
不是解析等价的清理。除此之外不允许产生任何其他解析差异。

默认打印 diff，不写文件；确认后加 --apply。
"""
import io, os, sys, difflib, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blank_lines import analyze


def read(path):
    with io.open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"      # 保持原换行符
    return text.replace("\r\n", "\n"), nl


def write_atomic(path, text, nl):
    data = text.replace("\n", nl).encode("utf-8")
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tidy-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)                     # 原子替换，中断不会留下半截文件
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def backup_path(path):
    fd, name = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)),
                                prefix=os.path.basename(path) + ".", suffix=".bak")
    os.close(fd)
    return name


def run(path, apply_changes):
    text, nl = read(path)
    lines = text.split("\n")
    drop, held, runs = analyze(lines)
    out = [l for i, l in enumerate(lines) if i not in drop]
    name = os.path.basename(path)
    print("%s：候选删除 %d 处｜保留待确认 %d 处｜连续空行 %d 处"
          % (name, len(drop), len(held), len(runs)))
    for i, why in held[:10]:
        print("    行%-5d 保留：%s" % (i + 1, why))
    for i in runs[:10]:
        print("    行%-5d 连续空行，需人工确认，不做批量压缩" % (i + 1))
    if not drop:
        return
    diff = difflib.unified_diff(lines, out, fromfile=name, tofile=name + "（清理后）",
                                lineterm="", n=1)
    body = list(diff)
    print("\n".join("    " + x for x in body[:60]))
    if len(body) > 60:
        print("    …… 共 %d 行差异" % len(body))
    if not apply_changes:
        print("    只读模式；确认后加 --apply 写入")
        return
    if [x for x in lines if x.strip()] != [x for x in out if x.strip()]:
        print("    正文行会被改动，已中止")
        return
    bak = backup_path(path)
    io.open(bak, "wb").write(text.replace("\n", nl).encode("utf-8"))
    write_atomic(path, "\n".join(out), nl)
    print("    已写入，备份：%s" % os.path.basename(bak))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for p in args:
        run(p, "--apply" in sys.argv)
