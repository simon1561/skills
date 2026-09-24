#!/usr/bin/env bash
# 把 skill 从出处软链接到各应用的入口目录。可重复运行，每次都会重建/校正链接。
#
# 两个出处：
#   自有 skill  ~/Documents/skills（本仓库，GitHub simon1561/skills）
#   第三方 skill ~/.agents/skills（npx skills 的安装位置）
#
# ~/.agents/skills 同时是 Codex、Antigravity、OpenCode 原生读取的入口，
# 所以这几个应用只需要在那里放自有 skill 的链接，第三方 skill 本来就在。
#
# 入口目录里若发现实体目录（被某个工具改回了拷贝），会先移到废纸篓再建链接，并在输出里标出。
#
# 用法：./link.sh        执行
#       ./link.sh -n     只检查，不改动

set -uo pipefail

OWN="$HOME/Documents/skills"
THIRD="$HOME/.agents/skills"
TRASH="$HOME/.Trash/skill-links-$(date +%Y%m%d-%H%M%S)"
DRY=0; [ "${1:-}" = "-n" ] && DRY=1

own=(stock-research svg-research-visuals report-writer)
lark=($(cd "$THIRD" && ls -d lark-* 2>/dev/null))
other=(cubox weread-skills general-video hyperframes hyperframes-animation hyperframes-audio
       hyperframes-cli hyperframes-core hyperframes-creative hyperframes-keyframes
       hyperframes-registry media-use)

changed=0; problems=0

ensure() {  # ensure <入口目录> <出处目录> <skill...>
  local dest="$1" src="$2"; shift 2
  [ -d "$dest" ] || { echo "  跳过：入口目录不存在 $dest"; return; }
  local name target link
  for name in "$@"; do
    target="$src/$name"; link="$dest/$name"
    if [ ! -d "$target" ]; then
      echo "  ! 出处缺少 $target"; problems=$((problems+1)); continue
    fi
    if [ -L "$link" ]; then
      [ "$link" -ef "$target" ] && continue   # 相对/绝对路径只要指向同一处都算正确
      echo "  ~ 改指向：$link"
      [ $DRY = 1 ] || { rm "$link" && ln -s "$target" "$link"; }
    elif [ -e "$link" ]; then
      if diff -rq -x .DS_Store -x __pycache__ -x "*.png" "$target" "$link" >/dev/null 2>&1; then
        echo "  ~ 实体目录换成软链（内容与出处一致）：$link"
      else
        echo "  ! 实体目录换成软链（内容与出处不同，旧版存废纸篓）：$link"; problems=$((problems+1))
      fi
      [ $DRY = 1 ] || { mkdir -p "$TRASH$dest" && mv "$link" "$TRASH$dest/" && ln -s "$target" "$link"; }
    else
      echo "  + 新建：$link"
      [ $DRY = 1 ] || ln -s "$target" "$link"
    fi
    changed=$((changed+1))
  done
}

broken() {  # 列出入口目录里的断链
  local dest="$1" l
  [ -d "$dest" ] || return
  for l in "$dest"/*; do
    [ -L "$l" ] && [ ! -e "$l" ] && { echo "  ! 断链：$l -> $(readlink "$l")"; problems=$((problems+1)); }
  done
}

# ── 清单：入口目录 ← 要链接的 skill ─────────────────────────────
echo "Claude Code"
ensure "$HOME/.claude/skills"     "$OWN"   "${own[@]}"
ensure "$HOME/.claude/skills"     "$THIRD" "${lark[@]}" "${other[@]}"

echo "Codex / Antigravity / OpenCode（~/.agents/skills）"
ensure "$HOME/.agents/skills"     "$OWN"   "${own[@]}"

echo "WorkBuddy"
ensure "$HOME/.workbuddy/skills"  "$OWN"   "${own[@]}"
ensure "$HOME/.workbuddy/skills"  "$THIRD" "${lark[@]}" "${other[@]}"

echo "豆包工作（飞书 skill 用它自带的，不链接）"
ensure "$HOME/DoubaoWork/skills"  "$OWN"   "${own[@]}"
ensure "$HOME/DoubaoWork/skills"  "$THIRD" "${other[@]}"

echo "断链检查"
for d in "$HOME/.claude/skills" "$HOME/.agents/skills" "$HOME/.workbuddy/skills" \
         "$HOME/DoubaoWork/skills" "$HOME/.codex/skills"; do broken "$d"; done

echo
[ $DRY = 1 ] && echo "（只检查模式，未改动）"
echo "需要调整 $changed 处，需要留意 $problems 处。"
[ -d "$TRASH" ] && echo "被替换的实体目录在：$TRASH"
exit 0
