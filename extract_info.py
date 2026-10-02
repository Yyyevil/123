"""Read a PDF, send its text to the DeepSeek API, and print the extracted fields as JSON.

Usage:
    python extract_info.py [path/to/file.pdf]

Environment:
    DEEPSEEK_API_KEY   required (or pass the key with --api-key "sk-...")

Output (stdout): a pure JSON string, e.g.
    {"姓名": "...", "电话": "...", "邮箱": "...", "日期": "..."}

Extraction logic lives in info_extractor.py so that batch_process.py can reuse it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import info_extractor as ie

HERE = Path(__file__).resolve().parent


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="用 DeepSeek API 从 PDF 文本中抽取结构化信息")
    parser.add_argument(
        "pdf",
        nargs="?",
        default=str(HERE / "test.pdf"),
        help="PDF 路径，默认为脚本同目录下的 test.pdf",
    )
    parser.add_argument("--api-key", default=None, help="DeepSeek API Key，默认读取环境变量 DEEPSEEK_API_KEY")
    parser.add_argument("--model", default=ie.MODEL, help=f"模型名，默认 {ie.MODEL}")
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    pdf_path = Path(args.pdf).expanduser()

    if not pdf_path.is_file():
        print(f"[错误] 找不到 PDF 文件：{pdf_path}")
        print("请放入文件，或指定路径：python extract_info.py 你的文件.pdf")
        return 1

    api_key = ie.resolve_api_key(args.api_key, fallback_dir=HERE)
    if not api_key:
        print(
            "[错误] 未找到 DeepSeek API Key。\n"
            "请设置环境变量后重试：\n"
            '  set DEEPSEEK_API_KEY=sk-xxxx        (cmd)\n'
            '  $env:DEEPSEEK_API_KEY="sk-xxxx"     (PowerShell)\n'
            f"或在 {HERE}\\.env 中写入一行：DEEPSEEK_API_KEY=sk-xxxx\n"
            "也可临时用参数传入：python extract_info.py test.pdf --api-key sk-xxxx"
        )
        return 1

    print(f"[1/3] 读取 PDF：{pdf_path}")
    text = ie.extract_pdf_text(pdf_path)
    if not text:
        print("[错误] 该 PDF 提取不到文本（可能是扫描件），需要 OCR 后再调用模型。")
        return 1
    print(f"      提取到 {len(text)} 个字符")
    print(text[:60].replace("\n", " ") + ("..." if len(text) > 60 else ""))

    print(f"[2/3] 调用 DeepSeek API（{args.model}）进行信息抽取...")
    try:
        data = ie.extract_fields(text, api_key, args.model)
    except Exception as exc:
        print(f"[错误] 调用接口失败：{exc.__class__.__name__}: {exc}")
        return 1

    print("[3/3] 提取结果（纯 JSON）：")
    print(data["_raw"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
