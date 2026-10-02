r"""通用表格提取批处理：遍历目录下的 PDF / 图片 → 视觉模型识别表格 → 动态生成 Excel。

（旧脚本 batch_process.py 仍然保留：它固定抽取"姓名/电话/邮箱/日期"并导出 employees.xlsx。
  这个脚本是通用版：列完全由模型识别出的表头决定，可以处理任意结构的表格。）

用法：
    python batch_extract.py                        # 处理 .\data，输出 .\output\extracted_tables.xlsx
    python batch_extract.py --input examples\in --output output\result.xlsx
    python batch_extract.py --hint "这是公司的价签账单"

特点：
- 列完全由模型识别出的表头决定，不同文档可以有不同的列数。
- 单个文件里的多张表会按表名分别落到不同的 sheet，同名表跨文件自动合并。
- 没有表格的文件只记进「汇总索引」，状态标为「跳过：无结构化数据」，不影响整批。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import info_extractor as ie
import multimodal_extractor as mx

HERE = Path(__file__).resolve().parent


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通用表格提取：PDF/图片 → 视觉模型 → 动态 Excel")
    parser.add_argument("--input", default=str(HERE / "data"), help="输入目录（PDF/图片），默认 ./data")
    parser.add_argument("--output", default=str(HERE / "output" / "extracted_tables.xlsx"), help="输出 Excel 路径")
    parser.add_argument("--json", default=None, help="可选：同时导出逐文件的原始 JSON")
    parser.add_argument("--api-key", default=None, help="DeepSeek API Key，默认读取 DEEPSEEK_API_KEY")
    parser.add_argument("--model", default=ie.VISION_MODEL, help=f"视觉模型，默认 {ie.VISION_MODEL}")
    parser.add_argument("--delay", type=float, default=1.0, help="每个文件之间的间隔秒数，默认 1（防限流）")
    parser.add_argument("--scale", type=float, default=2.0, help="PDF 渲染倍率，默认 2（约 144 DPI）")
    parser.add_argument("--hint", default="", help="给模型的额外提示，例如文档类型/语言")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个文件（调试用，0 表示全部）")
    parser.add_argument(
        "--layout",
        choices=["wide", "long"],
        default="wide",
        help="wide=每行一条记录（默认）；long=把档案卡型表格转成 来源文件/字段/值 三列，便于跨文件汇总",
    )
    parser.add_argument(
        "--no-normalize-headers",
        action="store_true",
        help="关闭列名同义归一（默认开启：商品/品名→商品名称、联系电话→电话，便于同类表合并）",
    )
    return parser.parse_args(argv[1:])


def collect_files(input_dir: Path) -> list[Path]:
    return sorted(
        (p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in mx.SUPPORTED_SUFFIXES),
        key=lambda p: str(p.relative_to(input_dir)).lower(),
    )


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    input_dir = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not input_dir.is_dir():
        print(f"[错误] 输入目录不存在：{input_dir}")
        print(f'请创建目录并放入 PDF/图片，例如：\n  mkdir "{input_dir}"')
        print(f'  或生成示例文件： .venv\\Scripts\\python.exe examples_gen.py "{input_dir}"')
        return 1

    files = collect_files(input_dir)
    if args.limit > 0:
        files = files[: args.limit]
    if not files:
        print(f"[错误] 目录里没有 PDF 或图片文件：{input_dir}")
        print(f'  可生成示例文件： .venv\\Scripts\\python.exe examples_gen.py "{input_dir}"')
        return 1

    api_key = ie.resolve_api_key(args.api_key, fallback_dir=HERE)
    if not api_key:
        print(
            "[错误] 未找到 DeepSeek API Key。\n"
            '  cmd:        set DEEPSEEK_API_KEY=sk-xxxx\n'
            '  PowerShell: $env:DEEPSEEK_API_KEY="sk-xxxx"\n'
            f"  或在 {HERE}\\.env 写入：DEEPSEEK_API_KEY=sk-xxxx"
        )
        return 1

    print(f"输入目录：{input_dir}")
    print(f"发现 {len(files)} 个文件，模型：{args.model}\n")

    results: list[dict] = []
    for index, path in enumerate(files, start=1):
        label = path.name if path.parent == input_dir else str(path.relative_to(input_dir))
        print(f"[{index}/{len(files)}] {label} ... ", end="", flush=True)
        result = mx.extract_structured(path, api_key, model=args.model, hint=args.hint, scale=args.scale)
        results.append(result)
        tables = result.get("tables", {})
        if tables:
            detail = "、".join(f"{name}({len(frame)}行)" for name, frame in tables.items())
            print(f"{len(tables)} 张表：{detail}")
        else:
            print(result["状态"])

        if args.delay and index < len(files):
            time.sleep(args.delay)

    sheets = mx.build_sheets(results, normalize=not args.no_normalize_headers)
    if args.layout == "long":
        sheets = mx.reshape_long(sheets)
    index_rows = mx.make_index_rows(results)
    mx.write_excel(sheets, output_path, index_rows)

    if args.json:
        json_path = Path(args.json).expanduser().resolve()
        payload = [
            {
                "文件名": result["文件名"],
                "状态": result["状态"],
                "表": {name: frame.to_dict(orient="records") for name, frame in result.get("tables", {}).items()},
            }
            for result in results
        ]
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n逐文件 JSON 已写入：{json_path}")

    import pandas as pd

    print("\n===== 汇总索引 =====")
    print(pd.DataFrame(index_rows).to_string(index=False, max_colwidth=30))
    print(f"\n共 {len(sheets)} 张表：" + "、".join(f"{name}({len(frame)}行)" for name, frame in sheets.items()))
    skipped = [result["文件名"] for result in results if not result.get("tables")]
    if skipped:
        print(f"跳过 {len(skipped)} 个文件（无表格）：{'、'.join(skipped)}")
    print(f"Excel 已生成：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
