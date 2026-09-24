#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付入口：按交付目标清理空行并做完整格式检查。

把三件事串成固定顺序，避免漏步：预览清理 → 确认写入 → 完整检查 → 按退出码放行。

用法：
  python3 deliver.py <文件.md> --target obsidian [--apply]
  python3 deliver.py <文件.md> --target markdown

  obsidian  段落之间不留空行（受保护结构的前后空行不动，见 SKILL.md 6.3）。
            不加 --apply 时只预览待清理的 diff，不改文件；加 --apply 时先清理再检查。
            --apply 视为已确认预览内容，脚本不校验是否真的预览过；清理会合并段落，
            属于有意的结构变换。
  markdown  按标准 Markdown 解析，段落间空行应当保留，不做任何清理。

退出码：0 自动检查通过（仍需人工复核），2 存在待处理项，1 用法或参数错误；
检查器返回其他非零码时原样透出，不并入 2。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script, args):
    sys.stdout.flush()            # 子进程直接写 stdout，先冲掉本进程缓冲以免顺序错乱
    return subprocess.run([sys.executable, os.path.join(HERE, script)] + args)


def main():
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 1

    path = argv[0]
    apply_ = False
    target, seen, i = None, 0, 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--target":
            following = argv[i + 1] if i + 1 < len(argv) else None
            if following is None or following.startswith("-"):
                print("--target 缺少取值，应为 obsidian 或 markdown")
                return 1
            target, seen, i = following, seen + 1, i + 2
            continue
        if arg.startswith("--target="):
            target, seen = arg.split("=", 1)[1], seen + 1
        elif arg == "--apply":
            apply_ = True
        else:
            print("未知参数：%s" % arg)
            return 1
        i += 1
    if seen > 1:
        print("--target 重复声明")
        return 1

    if target not in ("obsidian", "markdown"):
        print("必须用 --target 声明交付目标：obsidian 或 markdown")
        print("目标决定空行如何处理，无法从文件本身判断，因此不设默认值。")
        return 1
    if not os.path.exists(path):
        print("找不到文件：%s" % path)
        return 1
    if target == "markdown" and apply_:
        print("markdown 目标不做空行清理，--apply 无效")
        return 1

    if target == "obsidian":
        print("步骤 1／2　空行清理（%s）" % ("写入" if apply_ else "预览，不改文件"))
        tidy = run("tidy_blank_lines.py", [path] + (["--apply"] if apply_ else []))
        if tidy.returncode not in (0, 2):
            return tidy.returncode
        print("")

    label = "步骤 2／2" if target == "obsidian" else "格式检查"
    print("%s　格式检查（目标：%s）" % (label, target))
    checked = run("check.py", [path, "--target", target])

    print("")
    if checked.returncode == 0:
        print("自动检查通过，仍需按 SKILL.md 的清单人工复核。")
        return 0
    if checked.returncode != 2:
        print("格式检查未能正常完成，退出码 %d；请直接运行 check.py 查看原因。" % checked.returncode)
        return checked.returncode
    if target == "obsidian" and not apply_:
        print("存在待处理项。空行部分确认上面的 diff 无误后，重跑本命令并加 --apply；其余项需人工处理。")
    else:
        print("存在待处理项，处理后重跑本命令。")
    return 2


if __name__ == "__main__":
    sys.exit(main())
