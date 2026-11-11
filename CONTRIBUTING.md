# 贡献指南 CONTRIBUTING

## 三条底线

1. **零第三方运行时依赖。** 只用标准库。报告是手写 SVG，不是 ECharts；HTTP 只在可选路径里，用 `urllib`。
2. **测试不联网、不依赖时钟。** 所有随机性走固定 seed，所有日期从数据里读，不读 `today()`。
3. **改动星级必须改版本。** 任何影响 `stars` 取值的修改（权重、归一化、封顶、因子定义、信号源）都要：升 `INDEX_VERSION` → 更新 `METHODOLOGY.md` → 写 `CHANGELOG.md`。三者缺一，PR 不合。

## 本地开发

```bash
git clone https://github.com/OWNER/weibo-influence-index.git
cd weibo-influence-index

python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

pytest                       # 全绿才能提交
wii demo && wii build        # 生成 build/report.html
wii validate                 # 期望 PASS 10/10
```

可选：`pip install ruff`，然后 `ruff check src tests --select F,E9`。

## 提交前自检

```bash
pytest -q
wii demo --out data/demo
wii build --data data/demo --out build
wii validate --data data/demo
wii sensitivity --data data/demo
```

- [ ] 测试全绿（58 个用例）
- [ ] `wii validate` 10/10 通过
- [ ] 报告在浏览器里能打开，无外部请求（断网验证一次）
- [ ] 没有把 `data/raw/`、`.env`、cookie 文件带进提交

## 改因子 / 加因子的流程

新增一个因子不是加一个函数就完事，它要过五关：

1. **可测**：能用一句话说清"从哪些原始计数算出来"，且原始计数可人工核对。
2. **可复算**：在 `METHODOLOGY.md` 里写出公式，别人拿计算器能算出同一个数。
3. **有诊断**：`factors.py` 返回 `(value, diagnostics)`，诊断里包含所有中间量，报告能展开看。
4. **有测试**：边界（全 0、单点、封顶）、单调性、与既有因子的相关性。
5. **有校验**：如果它改变了排序，`wii validate` 必须仍然通过；如果通不过，先怀疑因子，不要改期望值。

**不要为了让某个案例好看而调权重。** 正确的顺序是：先检查该因子的测量是否有效，再谈权重。

## 代码风格

- Python ≥ 3.9，`from __future__ import annotations`，类型标注尽量全。
- 注释写"为什么"，不写"做了什么"。反直觉的参数必须有注释解释取舍。
- 中文用于用户可见文本（报告、CLI、文档），英文用于代码标识符与模块 docstring。
- 不引入 `pandas` / `numpy` / `requests`。如果某个计算非要它们，先开 issue 讨论，别直接提交。

## 提交信息

Conventional Commits 风格，中英不限：

```
feat(score): add censoring flag to half-life when decay is unobservable
fix(extract): keep same-day events ordered by source timestamp
docs(ethics): add takedown procedure template
test(factors): cover spillover with zero mentions
```

## 报 Bug 时请带上

```
wii --version
python --version
操作系统
复现命令
期望 vs 实际
build/validation.json（如相关）
```

数据类问题（某个事件日期错了、信源失效）请**直接给原始链接**，不要只描述结论。

## 不接受的内容

见 [ETHICS.md](ETHICS.md) §6。简言之：爬虫、真人黑榜、把极性塞进总分、跨年代排序、人脸/私生活信息。

## 许可

提交即表示同意以 MIT 许可发布你的贡献，并同意 [ETHICS.md](ETHICS.md) 中的使用约束。
