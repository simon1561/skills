#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
suite_dir="$(cd "$script_dir/../examples/visual-smoke-suite" && pwd)"
chrome_bin="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

if [[ ! -x "$chrome_bin" ]]; then
  echo "未找到 Chrome。请将 CHROME_BIN 设置为可执行的无头 Chrome 路径。" >&2
  exit 1
fi

if [[ "$#" -gt 0 ]]; then
  svg_files=()
  for item in "$@"; do
    if [[ "$item" = /* ]]; then
      svg_files+=("$item")
    else
      svg_files+=("$suite_dir/$item")
    fi
  done
else
  svg_files=("$suite_dir"/*.svg)
fi

for svg in "${svg_files[@]}"; do
  if [[ ! -f "$svg" ]]; then
    echo "未找到 SVG：$svg" >&2
    exit 1
  fi
  dimensions="$(perl -ne 'if (/<svg[^>]*\bwidth="([0-9]+)"[^>]*\bheight="([0-9]+)"/) { print "$1,$2"; exit }' "$svg")"
  if [[ ! "$dimensions" =~ ^[0-9]+,[0-9]+$ ]]; then
    echo "无法读取 SVG 画布尺寸：$svg" >&2
    exit 1
  fi

  output="${svg%.svg}.png"
  "$chrome_bin" \
    --headless --no-sandbox --disable-gpu \
    --force-device-scale-factor=1 --hide-scrollbars \
    --screenshot="$output" --window-size="$dimensions" \
    "file://$svg" >/dev/null 2>&1

  rendered_width="$(sips -g pixelWidth "$output" | awk '/pixelWidth/ { print $2 }')"
  rendered_height="$(sips -g pixelHeight "$output" | awk '/pixelHeight/ { print $2 }')"
  if [[ "$rendered_width,$rendered_height" != "$dimensions" ]]; then
    echo "渲染尺寸不匹配：$(basename "$svg")，预期 $dimensions，实际 $rendered_width,$rendered_height" >&2
    exit 1
  fi

  echo "已渲染 $(basename "$svg") → $(basename "$output") [$dimensions]"
done

"$script_dir/audit-svg-layout.sh" "$@"
