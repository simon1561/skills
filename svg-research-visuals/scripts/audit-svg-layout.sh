#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
suite_dir="$(cd "$script_dir/../examples/visual-smoke-suite" && pwd)"
chrome_bin="${CHROME_BIN:-}"
timeout_seconds="${SVG_BROWSER_TIMEOUT_SECONDS:-30}"
audit_page="file://$script_dir/audit-svg-layout.html"
failed=0

if [[ -z "$chrome_bin" ]]; then
  echo "ERROR: 未设置 CHROME_BIN，已拒绝启动系统日常 Chrome。" >&2
  echo "日常 SVG 审计请使用内置浏览器；维护回归基线时请安装 Chrome for Testing：" >&2
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
    if [[ "$item" = /* ]]; then svg_files+=("$item"); else svg_files+=("$suite_dir/$item"); fi
  done
else
  svg_files=("$suite_dir"/*.svg)
fi

for svg in "${svg_files[@]}"; do
  name="$(basename "$svg")"
  relative="$(python3 -c 'import os,sys; print(os.path.relpath(os.path.abspath(sys.argv[2]), os.path.abspath(sys.argv[1])))' "$suite_dir" "$svg")"
  encoded="$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$relative")"
  set +e
  dom="$(run_with_timeout "$timeout_seconds" "$chrome_bin" --headless --no-sandbox --disable-gpu --allow-file-access-from-files --dump-dom "$audit_page?file=$encoded" 2>/dev/null)"
  browser_status=$?
  set -e
  if [[ "$browser_status" -eq 124 ]]; then
    echo "FAIL $name"
    echo "  审计超时（${timeout_seconds}s），浏览器进程组已终止"
    failed=1
    continue
  elif [[ "$browser_status" -ne 0 ]]; then
    echo "FAIL $name"
    echo "  审计浏览器异常退出（状态 $browser_status）"
    failed=1
    continue
  fi
  audit="$(printf '%s' "$dom" | python3 -c 'import html,re,sys; s=sys.stdin.read(); m=re.search(r"<pre id=\"result\">(.*?)</pre>",s,re.S); print(html.unescape(m.group(1)).strip() if m else "NO_AUDIT_RESULT")')"
  if [[ "$audit" == "PASS" ]]; then
    echo "PASS $name"
  else
    echo "FAIL $name"
    printf '%s\n' "$audit" | sed 's/^/  /'
    failed=1
  fi
done

exit "$failed"
