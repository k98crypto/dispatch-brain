# DispatchBrain 使用手册（中文）

## 它到底是个什么东西

把它想成一个站在你和各家大模型中间的**调度员**：

- 你（或者 dsh 这类 Agent 软件）把请求发给它，它先**看一眼任务是什么**，
  再决定**派给哪个模型、花多少预算、推理开多强**，然后才真正调 API；
- 简单的活用便宜模型，难的活才用贵模型，看图的活只派给能看图的模型，
  批量改名这类机械活直接拦下来让脚本干，不花一分钱 token；
- 每一次调用的**场景、模型、成败、花了多少 token、耗时**都记进一本账，
  这本账就是它以后"越用越聪明"（自动调权）的依据。

它自己不写代码、不操作电脑。写代码的是 dsh，操作电脑的是 Cua 这类
执行层，**它只负责派活和记账**。好处是：执行层随便换，这个调度层不动。

---

## 一、安装（Windows，一次性）

### 1. 前置：Python 3.10 以上

打开 PowerShell 或 CMD 输入 `python --version`，能显示版本号即可。
没有就去 python.org 装一个（安装时勾选 "Add python.exe to PATH"）。

### 2. 下载代码

国内直连 GitHub 很慢，用镜像地址：

```powershell
git clone https://gh-proxy.com/https://github.com/k98crypto/dispatch-brain.git
cd dispatch-brain
```

没有 git 也可以在 GitHub 页面点 Code → Download ZIP 解压。

### 3. 安装

```powershell
pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
```

（清华镜像装得快。装完后 `dispatch-brain` 命令即可用。）

### 4. 填 API Key

把 `.env.example` 复制一份改名为 `.env`，填你实际有的 Key：

```ini
DEEPSEEK_API_KEY=sk-你的deepseek的key
DASHSCOPE_API_KEY=sk-你的阿里云百炼key
```

- DeepSeek 的 Key 在 platform.deepseek.com 的 API keys 页；
- DashScope（通义千问）Key 在阿里云百炼控制台开通后获取，
  **只在需要看图（视觉档）时才必须**，没有的话其他档照常工作；
- `.env` 会在启动时自动读取；它已被 `.gitignore` 排除，永远不会
  被提交到仓库。Key 只留在这台电脑上。

### 5. 启动网关

```powershell
dispatch-brain serve --port 8787
```

看到 Uvicorn 的启动日志就是成功了。**这个窗口在用 dsh 期间不要关**，
关掉窗口 = 调度员下班，dsh 会连不上（把 dsh 切回直连模型即可恢复）。

验证一下（另开一个窗口）：

```powershell
curl http://127.0.0.1:8787/healthz
```

返回 `{"ok":true,...}` 即正常。

---

## 二、接进 dsh（DeepSeek Harness）

1. 打开 dsh →「设置 → 模型」→ 添加自定义 Provider；
2. 类型选 **OpenAI-compatible**；
3. Base URL 填 `http://127.0.0.1:8787/v1`；
4. API Key 随便填一个非空值（如 `local`）；若你在 `.env` 里设了
   `DISPATCH_BRAIN_API_KEY`，就填那个；
5. 模型名填 **`auto`**，保存；
6. 之后在 dsh 里选这个模型干活，所有请求自动先过调度脑。

**想让它能看图**，还要在 dsh 的设置文件（settings.yaml）里给这个
模型加一行能力声明，否则 dsh 会在本地把图片拦下、根本发不出来：

```yaml
input: [text, image]
```

---

## 三、日常使用：四种点法

在任何接入的客户端里，"模型名"就是档位开关：

| 模型名 | 含义 | 什么时候用 |
|---|---|---|
| `auto` | 全自动分档 | 默认，绝大多数时候选它 |
| `auto-cheap` | 强制便宜档（flash + 低推理） | 明知道是小活，想再省一点 |
| `auto-strong` | 强制攻坚档（v4-pro + 高推理） | 明知道是硬活，免得它先派便宜模型试错 |
| `auto-vision` | 强制视觉档（qwen-vl-max） | 发图时客户端没自动带图标记的情况 |
| `deepseek-flash` 等注册表里的名字 | 直达某个模型 | 临时点名，记账照常 |

### `auto` 模式下它会怎么派活（真实规则）

| 你说的话 | 它的判断 | 派给谁 |
|---|---|---|
| "把这批照片批量重命名成日期格式" | 确定性操作 | 不调模型，返回"用脚本执行"的指令（零 token） |
| "翻译一句话：……" | 简单写作 | deepseek-flash，低推理，上限 4000 token |
| "这段代码报错，帮我看看" | 常规代码 | deepseek-flash，中推理 |
| "设计一个高并发架构，推导为什么这样设计" | 高难 | deepseek-v4-pro，高推理，上限 16000 token |
| （带截图）"这张图里写了什么" | 视觉 | qwen-vl-max |
| "在电脑上打开微信点开和张三的聊天" | GUI 操作 | qwen-vl-max（给执行层当眼睛），步数上限更紧 |
| "把这封邮件发送给客户" | 常规 + **高风险标记** | 正常派活，但决策带 `needs_human_confirm` |

最后一行的高风险标记目前在**命令行预览**和**自研 Agent 集成**时
能看到、能拦；dsh 这种封闭运行时不会读这个标记，它不会替 dsh
拦下发送动作——这条别误会。

### 命令行工具（不开网关也能用）

```powershell
dispatch-brain route "帮我把下载文件夹的图按日期改名"   # 预览它会怎么派（不真调模型）
dispatch-brain classify "这段代码为什么报错"            # 只看分类结果
dispatch-brain stats                                   # 账本统计：每个场景各模型的成功率/平均token
dispatch-brain suggest                                 # 按性价比给每个场景推荐模型（数据太少时会明说 insufficient_data）
```

`route` 适合在改完 `config/routes.yaml` 后先验证一遍派得对不对。

---

## 四、具体有什么用（对应真实场景）

1. **给 dsh 省钱**：dsh 原生的毛病是思考链长、机械步骤也开高推理。
   过调度脑后，机械活零 token、简单活被摁在 flash + 低推理 + token
   上限里，一次任务的账单结构立刻变样；而且每笔花销进账本，
   `stats` 一跑就知道钱花在哪个场景了。
2. **不用再手动切模型**：以前写代码切强模型、看图切视觉模型、
   闲聊切便宜模型，全靠脑子记。现在 dsh 里永远选 `auto` 一个，
   切换由它按内容自动完成，切错（比如拿纯文本模型看图）这种事
   结构上不再发生。
3. **单次请求烧不穿**：每一档都有 max_tokens 硬顶，网关强制截断；
   上游抽风（5xx）自动换兜底模型重试，不用你盯着。
4. **断网/省钱有本地兜底**：注册表里预置了 `qwen-local`（你自己的
   OpenAI 兼容端点，如家里服务器的 Ollama）。在 `.env` 里设
   `LOCAL_LLM_BASE_URL` 指向它之后，闲聊等简单场景在云端失败时
   会兜底到本地模型。
5. **给以后的电脑操作 Agent 当调度中枢**：等用 Cua 搭执行层时，
   GUI 任务的"眼睛"（视觉模型）和"脑子"（规划模型）由它统一派；
   自带的看门狗库（`dispatch_brain.watchdog`）嵌进执行层后，
   能治"重复点同一个按钮点到天荒地老"——步数/token/时长三重预算
   加上重复动作与状态无变化检测，卡住先换强模型重规划一次，
   再卡就停下来报人。
6. **越用越贴合你**：账本攒够样本后 `suggest` 给出的就是"你自己
   的任务里，哪个场景用哪个模型最划算"，而不是网上抄的通用结论。
   V2 会把这一步变成自动调权。

## 五、常见问题

- **网关必须一直开着吗？** 用接入的客户端期间要开着。就一个终端
  窗口的事；不用时关掉没有任何副作用，账本是本地文件。
- **能装在家里服务器上常开吗？** 可以，同一套命令在 Linux 上跑，
  然后客户端 Base URL 指向服务器地址即可；对外暴露时务必设
  `DISPATCH_BRAIN_API_KEY` 并配好你自己的隧道/反代。
- **端口被占用？** 换个数字，如 `--port 8788`，客户端 Base URL 同步改。
- **某个场景总派错怎么办？** 打开 `config/routes.yaml` 改对应行，
  或先用 `dispatch-brain route` 复现；分类关键词表在
  `dispatch_brain/classifier.py` 顶部，都是明文列表，改完即生效。
- **流式输出支持吗？** 支持（V1.1 起）。限制：流开始之后中途断掉
  无法换模型重发，只能结束并记为失败。
- **更新版本**：在项目目录 `git pull` 后重新 `pip install -e .` 即可。
