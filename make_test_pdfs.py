"""Generate several Chinese test PDFs (employee records) into a target folder."""
from __future__ import annotations

import sys
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
]

EMPLOYEES = [
    {
        "file": "employee_01.pdf",
        "title": "员工入职登记表",
        "lines": [
            "姓名：张伟",
            "联系电话：13812345678",
            "电子邮箱：zhangwei@example.com",
            "入职日期：2023年4月10日",
            "合同签署日期：2023-04-08",
            "备注：技术部后端工程师，转正日期 2023年7月10日。",
        ],
    },
    {
        "file": "employee_02.pdf",
        "title": "员工档案信息",
        "lines": [
            "姓名：李娜",
            "手机号码：13998887777",
            "公司座机：010-88886666",
            "邮箱：lina@example.com",
            "入职日期：2022年11月1日",
            "备注：市场部主管，2024年3月15日完成年度考核。",
        ],
    },
    {
        "file": "employee_03.pdf",
        "title": "候选人面试记录",
        "lines": [
            "候选人姓名：王强",
            "联系方式：13700001111",
            "电子邮箱：wangqiang@test.org",
            "面试日期：2024年6月18日",
            "期望到岗日期：2024-07-01",
            "评价：沟通表达清晰，建议进入二面。",
        ],
    },
    {
        "file": "employee_04.pdf",
        "title": "人员信息（字段不全）",
        "lines": [
            "姓名：陈静",
            "邮箱：chenjing@example.com",
            "备注：本记录故意不提供电话和日期，用于验证缺失字段的处理。",
        ],
    },
]


def pick_font() -> str | None:
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return path
    return None


def build(record: dict, out_dir: Path, font: str | None) -> Path:
    pdf = FPDF()
    pdf.set_title(record["title"])
    pdf.add_page()
    family = "helvetica"
    if font:
        pdf.add_font("cjk", "", font)
        family = "cjk"

    pdf.set_font(family, size=16)
    pdf.cell(0, 10, record["title"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    pdf.set_font(family, size=12)
    for line in record["lines"]:
        pdf.multi_cell(0, 8, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)

    path = out_dir / record["file"]
    pdf.output(str(path))
    return path


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
    out_dir.mkdir(parents=True, exist_ok=True)
    font = pick_font()
    if not font:
        print("警告：未找到中文字体，将退回 helvetica（中文会丢失）")
    for record in EMPLOYEES:
        path = build(record, out_dir, font)
        print("CREATED:", path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
