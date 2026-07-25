#!/usr/bin/env bash
# 将纯英文小标签使用的 Libre Franklin 子集化为 WOFF2，并以 base64 data-URI @font-face 内嵌进 SVG。
# 设计取舍：中文、数字和中英混排统一走系统中文无衬线栈（macOS 优先 PingFang）；
# 完整 CJK 字体动辄数 MB 且授权受限，从不内嵌，因此不承诺跨系统像素完全一致。
#
# 依赖：python3 + fonttools + brotli（pip install fonttools brotli）；OFL 字体 TTF 随包放在 scripts/fonts/。
# 幂等：重复运行会替换已内嵌的块，绝不重复叠加。
# 用法：
#   bash scripts/subset-fonts.sh                         # 默认处理示例集
#   bash scripts/subset-fonts.sh /path/to/file.svg       # 处理真实交付文件
#   bash scripts/subset-fonts.sh /path/to/svg-directory  # 处理目录第一层的所有 SVG
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fonts_dir="$script_dir/fonts"
default_suite="$script_dir/../examples/visual-smoke-suite"

command -v pyftsubset >/dev/null 2>&1 || { echo "ERROR: 未找到 pyftsubset（请先 pip install fonttools brotli）" >&2; exit 1; }

# 样图实际用到的字形：基本拉丁 + 数字 + 标点/符号（× – — 引号 → ← ↑ ↓ ▲ ▼ ≈ − ∓ ± 千分位/细空格 …）
UNICODES="U+0020-007E,U+00A0,U+00D7,U+2009,U+200A,U+2013,U+2014,U+2018,U+2019,U+201C,U+201D,U+2026,U+2190-2193,U+25B2,U+25BC,U+2248,U+2212,U+2213,U+00B1"

# 使用平行数组而非 declare -A，兼容 macOS 自带 Bash 3.2。
# 家族名必须与 SVG 中声明的 font-family 完全一致。
FAMILIES=("Libre Franklin" "Libre Franklin" "Libre Franklin" "Libre Franklin" "Libre Franklin")
WEIGHTS=(400 500 600 700 800)
FILES=(
  "LibreFranklin-Regular.ttf"
  "LibreFranklin-Medium.ttf"
  "LibreFranklin-SemiBold.ttf"
  "LibreFranklin-Bold.ttf"
  "LibreFranklin-ExtraBold.ttf"
)

# 解析目标：无参数时处理示例集；有参数时接受 SVG 文件或目录。
if [[ "$#" -eq 0 ]]; then
  INPUTS=("$default_suite")
else
  INPUTS=("$@")
fi

SVG_FILES=()
for item in "${INPUTS[@]}"; do
  if [[ ! -e "$item" && -f "$default_suite/$item" ]]; then
    item="$default_suite/$item"
  fi
  if [[ -f "$item" ]]; then
    [[ "$item" == *.svg ]] || { echo "ERROR: 目标文件不是 SVG：$item" >&2; exit 1; }
    SVG_FILES+=("$item")
  elif [[ -d "$item" ]]; then
    found=0
    while IFS= read -r svg; do
      SVG_FILES+=("$svg")
      found=1
    done < <(find "$item" -maxdepth 1 -type f -name '*.svg' -print | sort)
    [[ "$found" -eq 1 ]] || { echo "ERROR: 目录中未找到 SVG：$item" >&2; exit 1; }
  else
    echo "ERROR: 目标不存在：$item" >&2
    exit 1
  fi
done

[[ "${#SVG_FILES[@]}" -gt 0 ]] || { echo "ERROR: 未找到待处理的 SVG" >&2; exit 1; }

work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
face=""
for ((i=0; i<${#FILES[@]}; i++)); do
  fam="${FAMILIES[$i]}"; wt="${WEIGHTS[$i]}"; ttf="$fonts_dir/${FILES[$i]}"
  [[ -f "$ttf" ]] || { echo "ERROR: 缺少字体文件 $ttf（把对应 OFL TTF 放入 scripts/fonts/）" >&2; exit 1; }
  out="$work/${fam// /_}-$wt.woff2"
  pyftsubset "$ttf" --unicodes="$UNICODES" --flavor=woff2 \
    --output-file="$out" --layout-features='kern,tnum,lnum,onum,pnum' --no-hinting --desubroutinize
  b64="$(base64 < "$out" | tr -d '\n')"
  face+="@font-face{font-family:'$fam';font-style:normal;font-weight:$wt;font-display:swap;src:url(data:font/woff2;base64,$b64) format('woff2');}"
done

# 文本手术 + 硬校验（找不到锚点 / 引用了未内嵌的家族 / 内嵌块数量异常 → 报错退出，绝不静默成功）
python3 - "$face" "${SVG_FILES[@]}" <<'PY'
import sys, os, re
face, svgs = sys.argv[1], list(dict.fromkeys(sys.argv[2:]))
BEGIN, END = '<style id="__embedded-fonts">', '</style>'
block = BEGIN + face + END
embedded_families = set(re.findall(r"font-family:'([^']+)'", face))
REF = re.compile(r"font-family:(?:'|&#39;)([^'&;]+)")  # 兼容原始引号与 &#39; 实体两种写法
TARGET = ('Libre Franklin',)

if not svgs:
    print('ERROR: 未收到任何 SVG 路径', file=sys.stderr); sys.exit(1)

updated = 0
for f in svgs:
    name = os.path.basename(f)
    s = open(f, encoding='utf-8').read()
    refs = set(REF.findall(s))
    for fam in TARGET:
        if fam in refs and fam not in embedded_families:
            print('ERROR: %s 引用了 %s，但内嵌集合缺该家族' % (name, fam), file=sys.stderr); sys.exit(1)
    s = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END), '', s, flags=re.S)  # 幂等：先清旧块
    m = re.search(r'<svg\b[^>]*>', s)
    if not m:
        print('ERROR: %s 未找到 <svg> 锚点' % name, file=sys.stderr); sys.exit(1)
    s = s[:m.end()] + block + s[m.end():]
    open(f, 'w', encoding='utf-8').write(s)
    updated += 1

# 执行后逐张复核：内嵌块唯一，且每个被引用的目标家族都有对应 @font-face
for f in svgs:
    name = os.path.basename(f)
    s = open(f, encoding='utf-8').read()
    if s.count(BEGIN) != 1:
        print('ERROR: %s 内嵌块数量应为 1，实为 %d' % (name, s.count(BEGIN)), file=sys.stderr); sys.exit(1)
    refs = set(REF.findall(s))
    for fam in TARGET:
        if fam in refs and ("font-family:'%s'" % fam) not in s:
            print('ERROR: %s 缺少 %s 的内嵌 @font-face' % (name, fam), file=sys.stderr); sys.exit(1)

if updated == 0:
    print('ERROR: 未更新任何 SVG', file=sys.stderr); sys.exit(1)
print('OK: 已把字体子集内嵌到 %d 张 SVG（内嵌家族：%s）' % (updated, ', '.join(sorted(embedded_families))))
PY

echo "完成：纯英文标签字体子集已内嵌；中文与数字仍走系统中文无衬线栈。"
