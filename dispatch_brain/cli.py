"""Command-line entry: inspect routing decisions without running the server.

Examples:
    dispatch-brain classify "把这批图片批量重命名成日期格式"
    dispatch-brain route "帮我看看这个 Python 报错是什么原因"
    dispatch-brain stats
    dispatch-brain suggest
    dispatch-brain serve --port 8787
"""

from __future__ import annotations

import argparse
import json

from .classifier import classify
from .config import load_models, load_routes
from .logstore import LogStore
from .router import Router


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dispatch-brain")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cls = sub.add_parser("classify", help="classify a task text")
    p_cls.add_argument("text")

    p_route = sub.add_parser("route", help="classify + routing decision")
    p_route.add_argument("text")
    p_route.add_argument("--image", action="store_true", help="request carries an image")

    sub.add_parser("stats", help="show per scene x model statistics")
    sub.add_parser("suggest", help="show routing suggestions from the log")

    p_serve = sub.add_parser("serve", help="run the gateway")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8787)

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        from .gateway import run
        run(host=args.host, port=args.port)
        return 0

    if args.cmd == "classify":
        print(json.dumps(classify(args.text).to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "route":
        router = Router(load_routes(), load_models())
        c = classify(args.text, has_image=args.image)
        print(json.dumps({
            "classification": c.to_dict(),
            "decision": router.decide(c).to_dict(),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.cmd in ("stats", "suggest"):
        store = LogStore()
        data = store.stats() if args.cmd == "stats" else store.suggest()
        print(json.dumps(data, ensure_ascii=False, indent=2))
        store.close()
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
