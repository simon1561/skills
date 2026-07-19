#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
suite_dir="$(cd "$script_dir/../examples/visual-smoke-suite" && pwd)"
chrome_bin="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
audit_page="file://$script_dir/audit-svg-layout.html"
failed=0

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
  encoded="$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$name")"
  dom="$("$chrome_bin" --headless --no-sandbox --disable-gpu --allow-file-access-from-files --dump-dom "$audit_page?file=$encoded" 2>/dev/null)"
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
