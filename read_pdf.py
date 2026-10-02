"""Read a PDF file and print its extracted text to the terminal.

Usage:
    python read_pdf.py [path/to/file.pdf]

Defaults to ./test.pdf (same folder as this script).
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit(
        "pdfplumber 未安装。请先执行：\n"
        "    python -m pip install pdfplumber\n"
        "或在已激活的虚拟环境中执行：\n"
        "    python -m pip install -r requirements.txt"
    )


def resolve_pdf_path(argv: list[str]) -> Path:
    """Return the PDF path from argv, or <script dir>/test.pdf as default."""
    if len(argv) > 1:
        return Path(argv[1]).expanduser()
    return Path(__file__).resolve().parent / "test.pdf"


def extract_text(pdf_path: Path) -> list[str]:
    """Return one string per page."""
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"共 {total} 页，开始提取文本...\n")
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append(text)
            print(f"===== 第 {index} 页 / 共 {total} 页 =====")
            if text.strip():
                print(text)
            else:
                print("[本页没有可提取的文本，可能是扫描图片页]")
            print()
    return pages


def main(argv: list[str]) -> int:
    pdf_path = resolve_pdf_path(argv)
    print(f"目标文件: {pdf_path}")

    if not pdf_path.is_file():
        print(
            "\n[错误] 找不到该 PDF 文件。\n"
            "解决方案二选一：\n"
            "  1) 把 PDF 放到该路径后重新运行；\n"
            "  2) 直接指定文件：python read_pdf.py 你的文件.pdf"
        )
        return 1

    try:
        pages = extract_text(pdf_path)
    except Exception as exc:  # pdfminer/pdfplumber 对损坏文件会抛异常
        print(f"\n[错误] 解析 PDF 失败：{exc.__class__.__name__}: {exc}")
        return 1

    chars = sum(len(page) for page in pages)
    print("-" * 48)
    print(f"完成：{len(pages)} 页，共提取 {chars} 个字符。")
    if chars == 0:
        print("提示：文本为 0，说明这份 PDF 可能是纯扫描件（需要 OCR）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
