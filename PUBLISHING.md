# 发布清单 PUBLISHING

从本地目录到 GitHub 上可被审阅的公开仓库。全部命令在仓库根目录执行。

> 这份清单默认你把仓库放在 `github.com/<你的账号>/weibo-influence-index`。
> 请先全局替换 `OWNER`：README、pyproject、CITATION 里的占位符一共 4 处。

---

## 0. 发布前 5 分钟自检

```bash
pytest -q                     # 必须全绿（58 个用例）
wii demo && wii build && wii validate
wii explain --data data/demo --artist a01
```

- [ ] `wii validate` 输出 `PASS (10/10)`
- [ ] `build/report.html` 断网能打开，图表正常
- [ ] 仓库里没有 `.env`、cookie、`data/raw/`
- [ ] 没有真实自然人姓名、照片、真实信源链接混进 `data/demo`
- [ ] `docs/screenshot.png` 是最新的（重新截图，见 §4）

自动检查有没有真实数据残留：

```bash
grep -rn "weibo.com\|weibo.cn" data/ src/ docs/ | grep -v "example.com" || echo "clean"
```

---

## 1. 替换占位符

```bash
# macOS / Linux
grep -rl "OWNER" README.md pyproject.toml CITATION.cff 2>/dev/null | xargs sed -i '' 's/OWNER/<你的账号>/g'

# Windows (Git Bash)
grep -rl "OWNER" README.md pyproject.toml CITATION.cff 2>/dev/null | xargs sed -i 's/OWNER/<你的账号>/g'
```

替换后确认：

```bash
grep -rn "OWNER" . --exclude-dir=.git --exclude-dir=.venv --exclude-dir=build
```

---

## 2. 初始化并推送

```bash
git init -b main
git add .
git commit -m "feat: v1.0.0 — reproducible six-factor attention index"

# 先在 GitHub 上建空仓库（不要勾选 README/LICENSE/.gitignore）
git remote add origin https://github.com/<你的账号>/weibo-influence-index.git
git push -u origin main
```

推送前再看一眼将提交什么：

```bash
git status --short
git count-objects -vH      # 仓库体积，建议 < 5 MB
```

`data/demo`（约 900 KB）**应该提交**：它是确定性合成数据，读者 clone 下来即可 `wii build`，不必先跑生成器。这不是"数据泄漏"，是复现材料。

---

## 3. 仓库设置

| 项目 | 建议值 |
|---|---|
| Description | `A reproducible 1–10 star index of public attention on Weibo. Magnitude and sentiment polarity live on separate axes.` |
| Website | 留空，或 GitHub Pages 地址 |
| Topics | `reproducibility` `index` `weibo` `sentiment-analysis` `data-journalism` `python` `explainable` `synthetic-data` |
| Include in the home page | ✅ Releases ✅ Packages ❌ Deployments |
| Features | ✅ Issues ✅ Discussions（可选）❌ Wiki（文档在仓库里） |
| Social preview | 上传 `docs/screenshot.png` |

### 标签（Labels）

建 6 个就够：`bug` `enhancement` `methodology`（影响公式/权重的讨论）`data-quality`（事件或信源有误）`ethics`（合规相关）`good first issue`。

### 分支保护

`main`：要求 PR + CI 通过。**方法论的改动必须走 PR**，这是这个仓库唯一值得严格的地方。

---

## 4. 重新生成截图

```bash
wii build --data data/demo --out build
# 无头浏览器截首屏（Edge / Chrome 均可）
"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  --headless=new --disable-gpu --hide-scrollbars \
  --screenshot="$PWD/build/shot.png" --window-size=1200,2600 \
  "file:///$PWD/build/report.html"
```

然后裁到首屏（1200×2600 足够覆盖总览 + 双轴散点），另存为 `docs/screenshot.png`。

---

## 5. 打 tag 与 Release

```bash
git tag -a v1.0.0 -m "v1.0.0: six-factor attention index, reproducible and explainable"
git push origin v1.0.0
```

GitHub → Releases → Draft a new release → 选择 `v1.0.0`：

- 标题：`v1.0.0 — 可复算的六因子注意力指数`
- 正文：直接贴 `CHANGELOG.md` 的 1.0.0 段落
- 附件：上传 `build/report.html`（读者不装 Python 也能看报告）

---

## 6. 可选：GitHub Pages 自动发布报告

想让访客直接看报告，加一个 workflow（当前仓库**未**启用，路线图里有）：

```yaml
name: Pages
on:
  push:
    branches: [main]
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: github-pages
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: python -m pip install -e . && wii demo && wii build
      - run: cp build/report.html build/index.html
      - uses: actions/upload-pages-artifact@v3
        with: { path: build }
      - uses: actions/deploy-pages@v4
```

注意：Pages 是**公开可访问**的。如果将来换成真实数据，先回到 [ETHICS.md](ETHICS.md) §3 把清单走一遍。

---

## 7. 发布后第一周

- 在 README 顶部确认 CI 徽章能显示：
  ```markdown
  [![CI](https://github.com/<账号>/weibo-influence-index/actions/workflows/ci.yml/badge.svg)](https://github.com/<账号>/weibo-influence-index/actions/workflows/ci.yml)
  ```
- 发一条 issue 置顶，说明**方法论讨论欢迎、人格评价不欢迎**。
- 如果有人提"能不能加爬虫"：指到 [ETHICS.md](ETHICS.md) §6。
- 如果有人质疑星级：`wii explain` + 数据指纹就是答案，不用辩论。

---

## 8. 版本纪律

| 改动 | 版本 |
|---|---|
| 权重、归一化、封顶、因子定义、信号源 | **minor**（1.1.0），`INDEX_VERSION` 同步 |
| 破坏性变更（表结构、删除因子、改变星级语义） | **major**（2.0.0） |
| 文档、报告样式、CLI 输出格式 | **patch**（1.0.1） |

星级一旦发布就带着版本号走。**不要出现"同一个 v1.0.0 算出两个不同星级"**——那会让整个项目的可复算承诺失效。
