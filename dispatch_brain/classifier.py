"""Layer 1 — deterministic task classifier.

The routing decision itself must never burn the tokens it is trying to
save, so V1 classification is 100% rule-based: no LLM call, no embedding
call, sub-millisecond.

Design credit: the "never spend a model call on the routing decision"
principle follows the approach popularised by Semantic Router
(Aurelio Labs, https://github.com/aurelio-labs/semantic-router, MIT) —
they implement it with embedding similarity over example utterances;
V2 of this project may adopt that. This rule engine is an original
implementation tuned for a single user's agent workloads.

Output is a small JSON-able dict:
    {scene, difficulty, risk, needs_vision, executor}
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass
class Classification:
    scene: str        # deterministic | vision | gui | code | file_ops | data | writing | chat
    difficulty: str   # simple | standard | hard
    risk: str         # low | high  (high = sends/deletes/pays/publishes: human must confirm)
    needs_vision: bool
    executor: str     # script | llm | gui

    def to_dict(self) -> dict:
        return asdict(self)


# --- rule tables (order matters: first matching scene wins) -----------------

_VISION_HINTS = [
    "截图", "这张图", "图片里", "看一下这", "识别图", "图中",
    "screenshot", "this image", "in the picture", "ocr",
]

_DETERMINISTIC_HINTS = [
    "重命名", "批量改名", "改文件名", "格式转换", "转成pdf", "转成 pdf",
    "提取字段", "解压", "压缩成", "按日期归档", "文件分类放",
    "rename", "convert to pdf", "unzip", "batch rename",
]

_GUI_HINTS = [
    "点击", "打开微信", "打开小红书", "鼠标", "在软件里", "界面上点",
    "帮我在电脑上", "操作电脑", "打开浏览器搜索",
    "click on", "open the app", "use the mouse",
]

_CODE_HINTS = [
    "代码", "报错", "bug", "函数", "脚本", "python", "javascript",
    "typescript", "报错信息", "调试", "接口", "api返回", "git",
    "code", "debug", "stack trace", "exception", "compile",
]

_FILE_OPS_HINTS = [
    "文件夹", "整理文件", "移动文件", "这个目录", "磁盘", "清理下载",
    "folder", "move the files", "directory",
]

_DATA_HINTS = [
    "表格", "excel", "csv", "数据统计", "汇总一下", "透视",
    "spreadsheet", "statistics", "sum up the data",
]

_WRITING_HINTS = [
    "写一篇", "文案", "润色", "翻译", "改写", "写封邮件", "起草",
    "write a", "draft", "translate", "polish",
]

_HARD_HINTS = [
    "架构", "重构", "设计方案", "为什么", "原理", "复杂", "排查",
    "优化性能", "从零实现", "算法", "并发", "推导",
    "architecture", "refactor", "design a", "why does", "algorithm",
]

_SIMPLE_HINTS = [
    "一句话", "改个名", "这是什么意思", "简单", "翻译一句",
    "quick", "in one sentence", "what does this mean",
]

_RISK_HINTS = [
    "发送", "发给", "删除", "付款", "支付", "转账", "发布", "下单",
    "购买", "提交订单",
    "send it", "delete", "pay", "publish", "place the order",
]


def _contains_any(text: str, hints: list[str]) -> bool:
    return any(h in text for h in hints)


def classify(text: str, has_image: bool = False) -> Classification:
    """Classify one task/request text.

    `has_image` should be True when the request carries an image
    (e.g. an image_url part in an OpenAI-format message).
    """
    t = (text or "").lower()

    risk = "high" if _contains_any(t, _RISK_HINTS) else "low"

    if has_image or _contains_any(t, _VISION_HINTS):
        scene, executor, needs_vision = "vision", "llm", True
    elif _contains_any(t, _DETERMINISTIC_HINTS) and not _contains_any(t, _CODE_HINTS):
        # Mechanical operations (rename / convert / extract) should not
        # spend LLM tokens at all — a script does them deterministically.
        scene, executor, needs_vision = "deterministic", "script", False
    elif _contains_any(t, _GUI_HINTS):
        scene, executor, needs_vision = "gui", "gui", True
    elif _contains_any(t, _CODE_HINTS):
        scene, executor, needs_vision = "code", "llm", False
    elif _contains_any(t, _FILE_OPS_HINTS):
        scene, executor, needs_vision = "file_ops", "llm", False
    elif _contains_any(t, _DATA_HINTS):
        scene, executor, needs_vision = "data", "llm", False
    elif _contains_any(t, _WRITING_HINTS):
        scene, executor, needs_vision = "writing", "llm", False
    else:
        scene, executor, needs_vision = "chat", "llm", False

    if _contains_any(t, _HARD_HINTS) or len(t) > 800:
        difficulty = "hard"
    elif _contains_any(t, _SIMPLE_HINTS) or len(t) <= 40:
        difficulty = "simple"
    else:
        difficulty = "standard"

    return Classification(
        scene=scene,
        difficulty=difficulty,
        risk=risk,
        needs_vision=needs_vision,
        executor=executor,
    )


# Matches things like "task: ..." wrappers some agent runtimes add; kept
# intentionally tiny — classification works on raw user text as-is.
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WS.sub(" ", (text or "")).strip()
