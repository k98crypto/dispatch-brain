# 接入示例

DispatchBrain 对外就是一个 OpenAI 兼容端点。任何能填「自定义
Provider / Base URL」的客户端都可以接进来，然后把模型名写成
`auto`，剩下的分类、选模型、兜底、记账都由网关完成。

## 1. 启动网关

```bash
cp .env.example .env   # 填入你实际用的 API Key
pip install -e .
dispatch-brain serve --port 8787     # 默认监听 127.0.0.1:8787
```

## 2. DeepSeek Harness (dsh)

在 dsh 的「设置 → 模型」里添加一个自定义 Provider：

| 字段 | 值 |
|---|---|
| Provider 类型 | OpenAI-compatible |
| Base URL | `http://127.0.0.1:8787/v1` |
| API Key | 任意非空值（若网关设了 `DISPATCH_BRAIN_API_KEY` 则填那个） |
| 模型名 | `auto` |

之后 dsh 里选这个模型即可，所有请求先过调度脑。
也可以按需固定档位：`auto-cheap` / `auto-strong` / `auto-vision`。

> 注意：dsh 对手动添加的模型默认按纯文本处理。若要经网关发图片，
> 需要在 dsh 的设置文件里为该模型声明 `input: [text, image]`，
> 否则图片会被 dsh 在本地拦下、根本发不出来。

## 3. OpenAI SDK / 任意 OpenAI 兼容客户端

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8787/v1", api_key="local")
resp = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "帮我看看这段代码为什么报错"}],
)
print(resp.model)  # 响应里会带 dispatch_brain.routed_to 说明实际用的模型
```

## 4. Cua（computer-use 执行层）

DispatchBrain 不操作电脑，它只负责「派活给哪个模型」。GUI 场景
（scene=gui）路由到的视觉模型，就是给 computer-use 执行层当眼睛的：
把 Cua 的模型配置指向本网关、模型名填 `auto-vision`（或 `auto`），
即可让 GUI 任务自动使用视觉模型、文本子任务自动降档。

## 5. 只用命令行看看路由决策（不调任何模型）

```bash
dispatch-brain route "把这批照片批量重命名成日期格式"
dispatch-brain route "帮我设计一个高并发架构" --image
dispatch-brain stats      # 看日志里的 场景×模型 统计
dispatch-brain suggest    # 看基于日志的调权建议（V1 只建议、不自动改）
```
