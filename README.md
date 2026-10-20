# DispatchBrain 调度脑

**给 Agent 装一个会自己长大的调度脑：任务进来先分类，该用脚本的零 token，该用便宜模型的别烧贵模型，卡住了自动换强模型重规划，再卡就停下来报人。**

An OpenAI-compatible dispatch layer that sits between an agent runtime
(DeepSeek Harness, a Cua-based computer-use agent, the OpenAI SDK…)
and your model providers. It classifies every request, routes it to
the cheapest model that can actually do the job, enforces hard
budgets, detects no-progress loops, and logs everything — so the
routing table can learn from your real workload instead of guesses.

---

## 为什么需要它（三个真实痛点）

1. **烧 Token**：Agent 运行时（如 DeepSeek 官方 Harness / dsh）思考链很长，
   机械步骤也开着高推理，一次任务下来账单吓人。
2. **自己卡死自己**：同一个动作重复做、界面毫无变化，Agent 不自知，
   直到步数或预算耗尽。
3. **换模型靠手动**：写代码想用强模型、改文件名想用便宜模型、看图必须
   用视觉模型——全靠人切，切错了纯文本模型对着图片干瞪眼。

DispatchBrain 把这三件事从运行时里剥出来，做成一个独立、透明、
可手改的调度层：**运行时随便换，调度脑不动。**

## 架构（四层 + 一本账）

```
            任务 / 请求 (model: "auto")
                     │
   ┌─────────────────▼─────────────────┐
   │ 1. 分类器 classifier（规则，零调用） │  场景/难度/风险/是否需要视觉
   └─────────────────┬─────────────────┘
   ┌─────────────────▼─────────────────┐
   │ 2. 路由器 router（routes.yaml）     │  选模型+兜底链+推理档+预算上限
   └─────────────────┬─────────────────┘
   ┌─────────────────▼─────────────────┐
   │ 3. 网关 gateway（OpenAI 兼容）      │  转发（含流式 SSE）/故障兜底/封顶
   └─────────────────┬─────────────────┘
        DeepSeek / Qwen-VL / 本地模型 / …
   ┌─────────────────▼─────────────────┐
   │ 4. 看门狗 watchdog（运行时侧）      │  步数/token/时长预算 + 无进展检测
   └─────────────────┬─────────────────┘
   │ 5. 日志 logstore（SQLite）          │  场景×模型×成败×token×耗时
   └───────────────────────────────────┘   → suggest 给出调权建议（V2 自动应用）
```

核心路由哲学：

- **确定性操作零 token**：批量重命名、格式转换、字段提取这类事，
  分类器直接判给脚本执行，网关拒绝为它花一分钱模型费。
- **简单任务便宜模型 + 低推理**；**难任务才上强模型 + 高推理**。
- **视觉任务只去视觉模型**：纯文本模型没有"插件变出眼睛"这回事。
- **高风险动作标记人工确认**：发送/删除/付款/发布类请求，
  决策里带 `needs_human_confirm: true`，执行层必须停下来问人。
- **级联升级**：便宜模型先上，失败走兜底链换强模型（思路见下文 FrugalGPT）。

## 快速开始

```bash
git clone https://github.com/k98crypto/dispatch-brain.git
cd dispatch-brain
pip install -e .
cp .env.example .env        # 填入你实际使用的 API Key（只走环境变量）
dispatch-brain serve --port 8787
```

然后在任何 OpenAI 兼容客户端里：

- Base URL 填 `http://127.0.0.1:8787/v1`
- 模型名填 `auto`（或固定档位 `auto-cheap` / `auto-strong` / `auto-vision`）

dsh、Cua、OpenAI SDK 的具体接法见 [examples/integrations.md](examples/integrations.md)；
完整的中文安装与日常使用手册见 [docs/USAGE_zh.md](docs/USAGE_zh.md)。

不用起服务也能先看它怎么决策：

```bash
dispatch-brain route "把这批照片批量重命名成日期格式"
dispatch-brain route "帮我设计一个高并发的系统架构，并推导为什么这样设计"
dispatch-brain stats     # 场景×模型 的成功率/平均 token
dispatch-brain suggest   # 基于日志的调权建议
```

## 配置

- `config/models.yaml` — 模型注册表：供应商、模型名、Base URL、
  **Key 所在的环境变量名**（Key 本身永远不进配置文件）。
  预置 DeepSeek Flash / DeepSeek V4 Pro / Qwen-VL（通义千问视觉）/
  本地 qwen3:4b（自建 OpenAI 兼容端点），均为国内可直连。
- `config/routes.yaml` — 路由表：每个场景 × 难度 → 模型、兜底链、
  推理档位、token/步数/时长上限。这就是"脑子"本体，纯 YAML，可手改。
- `config/litellm_config.yaml` — 可选：用 LiteLLM 自带代理当网关引擎
  时的示例配置（见下文）。

## 看门狗怎么治"卡死"

运行时每步调用一次 `watchdog.observe(工具名, 参数, 状态哈希, 本步token)`：

- 同一动作重复 ≥3 次，或状态连续 ≥3 步无变化 → 返回 `replan_escalate`：
  中断、压缩上下文、换强模型重规划（只允许一次）；
- 重规划后再次卡住，或步数/token/时长任一硬预算超限 → 返回 `stop`，
  停下来向人报告，绝不静默烧钱。

## 自学习（"长脑子"的进度）

- **V1（当前）**：规则分类 + 静态路由表 + 预算/看门狗 + 全量日志；
  `suggest` 按「成功率 ÷ 平均 token」给每个场景算性价比最优模型，
  **只建议、不自动改表**——数据不够时它会直说 `insufficient_data`。
- **V2**：日志量达标后自动调权（带回滚）；分类器升级为语义路由
  （示例句向量匹配，零 LLM 调用，思路见 Semantic Router）。
- **V3**：任务自动拆解与多执行器并行（暂缓——先把 V1/V2 用出数据）。

## 借鉴与致谢（重要）

按本项目立项时的约定：**所有借用必须公开**。V1 的代码为原创
（MIT），未复制任何第三方项目的代码；下列项目以「依赖」或
「设计借鉴」的方式影响了本项目，逐项列明：

| 项目 | 许可证 | 关系 | 说明 |
|---|---|---|---|
| [LiteLLM](https://github.com/BerriAI/litellm)（BerriAI） | MIT（企业版目录除外） | **可选依赖** | 提供 `config/litellm_config.yaml` 示例，可用其代理替代内置转发器；未 vendoring 其代码 |
| [RouteLLM](https://github.com/lm-sys/RouteLLM)（LMSYS） | Apache-2.0 | **设计借鉴** | 「强/弱模型 + 按请求权衡成本质量」的路由思想来源；该项目自 2024-08 起停更，故不作依赖 |
| [Semantic Router](https://github.com/aurelio-labs/semantic-router)（Aurelio Labs） | MIT | **设计借鉴** | 「路由决策本身零 LLM 调用」原则与示例句路由思路；V2 计划将其列为可选依赖 |
| [FrugalGPT](https://arxiv.org/abs/2305.05176)（Chen et al., 2023） | 论文（无代码） | **设计借鉴** | 级联策略：便宜模型先试、验不过再升级 |
| [Arch / Arch-Router](https://github.com/katanemo/archgw)（Katanemo） | 仓库 Apache-2.0；其路由模型为 Katanemo 自定义许可证 | **仅理念参考** | 「小模型专职做路由决策」的理念；因其模型许可证非标准开源，本项目未使用其模型与代码 |
| [Cua](https://github.com/trycua/cua) | MIT | **生态搭配** | 推荐的 computer-use 执行层底座；本项目负责"派活给哪个模型"，Cua 负责"动手操作电脑"，两者经 OpenAI 兼容接口组合 |
| [FastAPI](https://github.com/fastapi/fastapi) / httpx / PyYAML / uvicorn | MIT / BSD / MIT / BSD | **运行时依赖** | 常规依赖，版本约束见 `pyproject.toml` |

若后续版本直接引入或改编上述任何项目的代码，将在对应源文件头部
注明出处与原始许可证，并在本节更新。

## 安全说明

- **Key 只走环境变量**，不进 YAML、不进仓库、不进日志。
- **高风险标记不是摆设**：执行层收到 `needs_human_confirm: true`
  必须停下等人确认（发送/删除/付款/发布）。
- **LiteLLM 锁版本**：2026 年 3 月 LiteLLM 曾遭 PyPI 供应链投毒，
  如使用可选依赖，请只装已核实的固定版本（示例中为 `1.80.0`），
  不要无条件 `pip install -U`。
- 网关默认只监听 `127.0.0.1`；要对外监听请同时设置
  `DISPATCH_BRAIN_API_KEY` 并自行加反向代理/TLS。

## 已知限制（V1）

- 流式（SSE）转发已支持（V1.1）：分块原样透传，末尾 usage 记入日志；
  但流式的故障兜底只在**首字节发出之前**有效——流一旦开始，中途断掉
  无法换模型重发（会重复输出），只能结束并记为失败。这是所有流式
  代理的共同限制。分类只看最后一条 user 消息。
- 分类器是规则引擎，覆盖常见场景；刁钻表述可能分错类——
  分错的代价是选错档位，日志里看得到，路由表改一行即可纠正。
- `suggest` 的性价比公式是最简版（成功率 ÷ 平均 token），
  不区分任务内在价值，V2 会引入难度加权。

## 测试

```bash
python -m unittest discover -s tests -v   # 21 个用例，零额外依赖
```

## License

[MIT](LICENSE) © 2026 k98crypto
