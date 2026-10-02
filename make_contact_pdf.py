"""Generate sample_contact.pdf: a Chinese-style document containing 姓名/电话/邮箱/日期."""
from __future__ import annotations

import sys
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

out = Path(sys.argv[1] if len(sys.argv) > 1 else "sample_contact.pdf")

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
]


def pick_font() -> str | None:
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return path
    return None


CONTENT = [
    ("客户信息登记表", 16),
    ("", 12),
    ("姓名：张伟", 12),
    ("联系电话：13812345678", 12),
    ("备用电话：021-65432100", 12),
    ("电子邮箱：zhangwei@example.com", 12),
    ("", 12),
    ("签约日期：2024年5月20日", 12),
    ("最近一次回访：2025年3月8日", 12),
    ("", 12),
    ("备注：客户希望以邮件方式接收后续账单，", 12),
    ("并在工作日9:00-18:00之间电话联系。", 12),
]

pdf = FPDF()
pdf.set_title("sample contact info")
pdf.add_page()

font = pick_font()
if font:
    pdf.add_font("cjk", "", font)
    family = "cjk"
else:
    family = "helvetica"

for line, size in CONTENT:
    pdf.set_font(family, size=size)
    if line:
        pdf.cell(0, 9, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.ln(4)

pdf.output(str(out))
print("CREATED:", out.resolve())
