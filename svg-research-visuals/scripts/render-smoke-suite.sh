#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
suite_dir="$(cd "$script_dir/../examples/visual-smoke-suite" && pwd)"
chrome_bin="${CHROME_BIN:-}"
timeout_seconds="${SVG_BROWSER_TIMEOUT_SECONDS:-30}"

if [[ -z "$chrome_bin" ]]; then
  echo "ERROR: 未设置 CHROME_BIN，已拒绝启动系统日常 Chrome。" >&2
  echo "请把 CHROME_BIN 指向独立浏览器；推荐安装 Chrome for Testing：" >&2
  echo "  npx @puppeteer/browsers install chrome@stable" >&2
  exit 1
fi

case "$chrome_bin" in
  /Applications/Google\ Chrome.app/*)
    echo "ERROR: 禁止用 /Applications/Google Chrome.app 执行 headless 任务，以免卡死后占住日常 Chrome 实例。" >&2
    echo "请将 CHROME_BIN 指向 Chrome for Testing 或其他独立 Chromium。" >&2
    exit 1
    ;;
esac

if [[ ! -x "$chrome_bin" ]]; then
  echo "ERROR: CHROME_BIN 不可执行：$chrome_bin" >&2
  exit 1
fi

resolved_chrome_bin="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$chrome_bin")"
case "$resolved_chrome_bin" in
  /Applications/Google\ Chrome.app/*)
    echo "ERROR: CHROME_BIN 最终指向系统日常 Chrome：$resolved_chrome_bin" >&2
    echo "即使通过符号链接引用也禁止用于 headless 任务；请改用 Chrome for Testing 或其他独立 Chromium。" >&2
    exit 1
    ;;
esac

run_with_timeout() {
  local seconds="$1"
  shift
  python3 - "$seconds" "$@" <<'PY'
import os
import signal
import subprocess
import sys

seconds = float(sys.argv[1])
command = sys.argv[2:]
process = subprocess.Popen(command, start_new_session=True)
try:
    return_code = process.wait(timeout=seconds)
except subprocess.TimeoutExpired:
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    sys.exit(124)
sys.exit(return_code)
PY
}

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
  set +e
  run_with_timeout "$timeout_seconds" "$chrome_bin" \
    --headless --no-sandbox --disable-gpu \
    --force-device-scale-factor=1 --hide-scrollbars \
    --screenshot="$output" --window-size="$dimensions" \
    "file://$svg" >/dev/null 2>&1
  browser_status=$?
  set -e
  if [[ "$browser_status" -eq 124 ]]; then
    echo "渲染超时（${timeout_seconds}s），浏览器进程组已终止：$(basename "$svg")" >&2
    exit 1
  elif [[ "$browser_status" -ne 0 ]]; then
    echo "渲染浏览器异常退出（状态 $browser_status）：$(basename "$svg")" >&2
    exit 1
  fi

  rendered_width="$(sips -g pixelWidth "$output" | awk '/pixelWidth/ { print $2 }')"
  rendered_height="$(sips -g pixelHeight "$output" | awk '/pixelHeight/ { print $2 }')"
  if [[ "$rendered_width,$rendered_height" != "$dimensions" ]]; then
    echo "渲染尺寸不匹配：$(basename "$svg")，预期 $dimensions，实际 $rendered_width,$rendered_height" >&2
    exit 1
  fi

  echo "已渲染 $(basename "$svg") → $(basename "$output") [$dimensions]"
done

bash "$script_dir/audit-svg-layout.sh" "$@"
