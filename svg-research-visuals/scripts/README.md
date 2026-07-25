# scripts/ 使用说明

本目录的脚本在**部署环境**（本机 / CI）运行，用于字体内嵌以及低频的视觉回归基线维护。日常 SVG 自检优先使用 Codex 内置浏览器：从 skill 根目录启动本地 HTTP server，打开 `scripts/audit-svg-layout.html`，读取 `#result` 并直接截图目视检查；日常流程不产出 PNG。

`render-smoke-suite.sh` 与 `audit-svg-layout.sh` 只用于更新或核验 `examples/visual-smoke-suite/` 的回归基线。它们不会寻找系统 Chrome，必须显式设置 `CHROME_BIN`，而且禁止指向 `/Applications/Google Chrome.app`。

## 可执行权限

脚本随包发布时可能不带可执行位。两种运行方式任选其一：

```bash
# 方式一（推荐，免权限）：显式解释器
bash scripts/render-smoke-suite.sh
bash scripts/audit-svg-layout.sh
bash scripts/subset-fonts.sh
python3 scripts/audit-style.py

# 方式二：先补可执行位，再直接运行
chmod +x scripts/*.sh
./scripts/render-smoke-suite.sh
```

文档与 `SKILL.md` 中的示例统一使用「方式一」，因此无论是否设置可执行位都能运行。

## 脚本清单

| 脚本 | 作用 | 依赖 |
|---|---|---|
| `audit-style.py` | 静态样式闸门：a11y 属性 / 等宽数字 / 禁用旧色值与纯白底，并报告状态色·风险色用量。返回码非 0 即 FAIL。 | python3 |
| `audit-svg-layout.sh` + `audit-svg-layout.html` | 低频回归维护：用 `CHROME_BIN` 指定的独立 Chromium 加载每张 SVG，按浏览器真实字形边界（转墨迹盒）审计越界、容器越界、文字重叠与紧凑组件留白。无参数审计全套，或传文件名/路径审计指定图。每个浏览器调用都受超时保护。 | Chrome for Testing 或独立 Chromium（必须显式设置 `CHROME_BIN`）、python3 |
| `render-smoke-suite.sh` | 低频回归维护：按各 SVG 原始宽高渲染为同名 PNG 并校验尺寸；结束后自动调用布局审计。每个浏览器调用都受超时保护。 | Chrome for Testing 或独立 Chromium（必须显式设置 `CHROME_BIN`）、python3、macOS `sips`（其他平台改用等价取图工具） |
| `subset-fonts.sh` | 将纯英文小标签使用的 Libre Franklin 子集化为 WOFF2，并以 base64 `@font-face`（`<style id="__embedded-fonts">`）内嵌进示例或指定的真实交付 SVG。 | macOS Bash 3.2+、python3 + fonttools + brotli；随包 OFL 字体 TTF |

## subset-fonts.sh：内嵌目标西文字

1. `pip install fonttools brotli`
2. Libre Franklin 静态字重及 OFL 许可文件已经放在 `scripts/fonts/`，字体来自官方 `googlefonts/Libre-Franklin` 仓库。中文、数字和 hero 大数字统一使用系统中文无衬线栈，不内嵌 CJK 字体。
3. 按目标运行：

```bash
bash scripts/subset-fonts.sh                          # 默认处理25张示例
bash scripts/subset-fonts.sh /path/to/output.svg      # 处理一张真实交付图
bash scripts/subset-fonts.sh /path/to/svg-directory  # 处理目录第一层所有SVG
```

脚本**幂等**（重复运行替换而非叠加内嵌块），并在以下情况报错退出，绝不静默成功：缺少 `pyftsubset`、缺少字体文件、某张 SVG 找不到 `<svg>` 锚点、SVG 引用了未内嵌的家族、或执行后复核发现内嵌块缺失/重复。

> 未运行本脚本时，纯英文标签由 Libre Franklin 回退到 Helvetica/Arial，中文和数字由 PingFang/微软雅黑/思源黑体系统栈显示，全程无 `@import` / 网络字体；运行后离线可命中 Libre Franklin。完整 CJK 字体不内嵌，因此不同操作系统不承诺像素完全一致。脚本兼容 macOS 自带 Bash 3.2，不要求 Homebrew Bash。

## 交付前建议顺序

### 日常画图：内置浏览器，不产 PNG

```bash
cd /path/to/svg-research-visuals
python3 -m http.server 8765 --bind 127.0.0.1
```

在内置浏览器打开：

```text
http://127.0.0.1:8765/scripts/audit-svg-layout.html?file=01-%E8%B6%8B%E5%8A%BF%E6%95%B0%E6%8D%AE%E5%9B%BE.svg
```

等待 `#result` 从 `PENDING` 变成 `PASS` 或 `FAIL`，读取完整结果并截图目视检查。suite 外文件需传相对 `examples/visual-smoke-suite/` 的路径，例如 skill 根目录文件为 `../../example.svg`。必须使用 `http://`，不能使用 `file://`。检查完成后停止 HTTP server。

### 维护回归基线：独立 Chromium，产出 PNG

```bash
python3 scripts/audit-style.py          # 1. 静态样式闸门
bash scripts/subset-fonts.sh            # 2.（可选，离线自包含）内嵌字体子集
export CHROME_BIN="/path/to/chrome-for-testing"
bash scripts/render-smoke-suite.sh      # 3. 重渲染 PNG + 自动布局审计
# 4. 打开 examples/visual-smoke-suite/review-gallery.html 做跨版式人工复检
```

推荐安装独立的 Chrome for Testing：

```bash
npx @puppeteer/browsers install chrome@stable
```

脚本默认单次浏览器调用超时为 30 秒，可用 `SVG_BROWSER_TIMEOUT_SECONDS` 调整。超时后会终止整个浏览器进程组，避免留下无窗口的 headless 进程。未设置 `CHROME_BIN`、路径不可执行，或路径指向 `/Applications/Google Chrome.app` 时，脚本都会直接报错退出。
