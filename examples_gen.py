r"""生成多形态测试样例：带表格的 PDF、双表 PDF、档案 PDF、手写价签图、表格截图、无表格段落图。

用法：
    python examples_gen.py examples\in
"""

from __future__ import annotations

import sys
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CJK_FONTS = [
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\simkai.ttf",
]


def pick_font() -> str | None:
    for path in CJK_FONTS:
        if Path(path).is_file():
            return path
    return None


def pick_hand_font() -> str:
    for path in (r"C:\Windows\Fonts\simkai.ttf", r"C:\Windows\Fonts\msyh.ttc"):
        if Path(path).is_file():
            return path
    return pick_font() or r"C:\Windows\Fonts\arial.ttf"


# --------------------------------------------------------------------------- PDF
def new_pdf(title: str, font: str | None) -> tuple[FPDF, str]:
    pdf = FPDF()
    pdf.set_title(title)
    pdf.add_page()
    family = "helvetica"
    if font:
        pdf.add_font("cjk", "", font)
        family = "cjk"
    return pdf, family


def draw_table(pdf: FPDF, family: str, headers: list[str], rows: list[list[str]], widths: list[int]) -> None:
    pdf.set_font(family, size=11)
    pdf.set_fill_color(230, 236, 245)
    for header, width in zip(headers, widths):
        pdf.cell(width, 8, header, border=1, align="center", fill=True)
    pdf.ln()
    for row in rows:
        for value, width in zip(row, widths):
            pdf.cell(width, 8, value, border=1, align="center")
        pdf.ln()


def make_invoice_pdf(out_dir: Path, font: str | None) -> Path:
    pdf, family = new_pdf("商品清单", font)
    pdf.set_font(family, size=15)
    pdf.cell(0, 10, "商品清单", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(family, size=11)
    pdf.cell(0, 7, "单据编号：FP-2024-0088    日期：2024年6月18日", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    draw_table(
        pdf,
        family,
        ["商品名称", "规格", "数量", "单价", "金额"],
        [
            ["苹果", "500g", "3", "5.50", "16.50"],
            ["牛奶", "1L", "2", "12.00", "24.00"],
            ["鸡蛋", "10枚", "1", "9.90", "9.90"],
            ["大米", "5kg", "1", "39.00", "39.00"],
        ],
        [40, 30, 20, 25, 25],
    )
    pdf.ln(3)
    pdf.set_font(family, size=11)
    pdf.cell(0, 8, "合计：89.40 元", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    path = out_dir / "invoice_table.pdf"
    pdf.output(str(path))
    return path


def make_two_tables_pdf(out_dir: Path, font: str | None) -> Path:
    pdf, family = new_pdf("月度对账单", font)
    pdf.set_font(family, size=15)
    pdf.cell(0, 10, "月度对账单", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    pdf.set_font(family, size=12)
    pdf.cell(0, 8, "表1：销售明细", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    draw_table(
        pdf,
        family,
        ["产品", "批次号", "销售日期", "销量", "销售额"],
        [
            ["洗衣液", "B20240601", "2024-06-01", "120", "1440.00"],
            ["洗手液", "B20240605", "2024-06-05", "86", "774.00"],
            ["纸巾", "B20240612", "2024-06-12", "240", "1200.00"],
        ],
        [32, 34, 32, 22, 28],
    )

    pdf.ln(6)
    pdf.set_font(family, size=12)
    pdf.cell(0, 8, "表2：员工信息", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    draw_table(
        pdf,
        family,
        ["姓名", "工号", "部门", "电话", "入职日期"],
        [
            ["张伟", "E1001", "技术部", "13812345678", "2023-04-10"],
            ["李娜", "E1002", "市场部", "13998887777", "2022-11-01"],
            ["王强", "E1003", "财务部", "13700001111", "2021-09-15"],
        ],
        [26, 26, 28, 36, 32],
    )
    path = out_dir / "two_tables.pdf"
    pdf.output(str(path))
    return path


def make_profile_pdf(out_dir: Path, font: str | None) -> Path:
    """档案类：键值对形式的结构化数据（没有严格表格线）。"""
    pdf, family = new_pdf("员工档案", font)
    pdf.set_font(family, size=15)
    pdf.cell(0, 10, "员工档案卡", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font(family, size=12)
    for line in [
        "姓名：赵敏",
        "工号：E2088",
        "部门：供应链部",
        "职位：采购主管",
        "联系电话：13600002222",
        "电子邮箱：zhaomin@example.com",
        "入职日期：2020年3月2日",
        "月薪：18500 元",
    ]:
        pdf.cell(0, 9, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    path = out_dir / "profile_record.pdf"
    pdf.output(str(path))
    return path


# --------------------------------------------------------------------------- 图片
def make_receipt_image(out_dir: Path) -> Path:
    """模拟手写价签账单：白底、深蓝笔迹、轻微倾斜。"""
    width, height = 640, 520
    image = Image.new("RGB", (width, height), (252, 250, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle([16, 16, width - 17, height - 17], outline=(180, 180, 175), width=2)

    font_path = pick_hand_font()
    title_font = ImageFont.truetype(font_path, 34)
    text_font = ImageFont.truetype(font_path, 26)
    ink = (25, 45, 120)

    draw.text((190, 40), "价签账单", font=title_font, fill=ink)
    draw.line([(60, 95), (width - 60, 95)], fill=ink, width=2)

    header_y = 120
    for x, text in ((70, "商品"), (250, "数量"), (370, "单价"), (500, "金额")):
        draw.text((x, header_y), text, font=text_font, fill=ink)

    items = [
        ("苹果", "3", "5.50", "16.50"),
        ("牛奶", "2", "12.00", "24.00"),
        ("面包", "1", "8.50", "8.50"),
        ("总计", "", "", "49.00"),
    ]
    y = header_y + 48
    for name, qty, price, amount in items:
        draw.text((70, y), name, font=text_font, fill=ink)
        draw.text((255, y), qty, font=text_font, fill=ink)
        draw.text((370, y), price, font=text_font, fill=ink)
        draw.text((495, y), amount, font=text_font, fill=ink)
        y += 52

    draw.line([(60, y + 6), (width - 60, y + 6)], fill=ink, width=2)
    image = image.rotate(-1.2, resample=Image.BICUBIC, expand=False, fillcolor=(252, 250, 245))
    path = out_dir / "price_tag_handwritten.png"
    image.save(path)
    return path


def make_table_screenshot(out_dir: Path) -> Path:
    """模拟屏幕截图：表格 + 底部统计，结构扁平。"""
    width, height = 760, 420
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = pick_font() or r"C:\Windows\Fonts\arial.ttf"
    title_font = ImageFont.truetype(font_path, 24)
    cell_font = ImageFont.truetype(font_path, 20)

    draw.text((30, 22), "2024年6月 商品销售统计", font=title_font, fill=(20, 20, 20))
    headers = ["日期", "商品", "销量", "单价", "销售额"]
    widths = [170, 160, 110, 120, 150]
    x0, y0, row_h = 30, 78, 46

    x = x0
    for header, width in zip(headers, widths):
        draw.rectangle([x, y0, x + width, y0 + row_h], fill=(232, 238, 248), outline=(120, 130, 150))
        draw.text((x + 12, y0 + 12), header, font=cell_font, fill=(20, 20, 20))
        x += width

    rows = [
        ["2024-06-01", "洗衣液", "120", "12.00", "1440.00"],
        ["2024-06-05", "洗手液", "86", "9.00", "774.00"],
        ["2024-06-12", "纸巾", "240", "5.00", "1200.00"],
        ["2024-06-20", "牙膏", "64", "18.50", "1184.00"],
    ]
    y = y0 + row_h
    for row in rows:
        x = x0
        for value, width in zip(row, widths):
            draw.rectangle([x, y, x + width, y + row_h], outline=(150, 158, 172))
            draw.text((x + 12, y + 12), value, font=cell_font, fill=(20, 20, 20))
            x += width
        y += row_h

    draw.text((30, y + 20), "合计销量：510 件    合计销售额：4598.00 元", font=cell_font, fill=(60, 60, 60))
    path = out_dir / "sales_table_screenshot.png"
    image.save(path)
    return path


def make_plain_image(out_dir: Path) -> Path:
    """完全没有表格的图片：只用来验证"无结构化数据"分支。"""
    width, height = 700, 300
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = pick_font() or r"C:\Windows\Fonts\arial.ttf"
    title_font = ImageFont.truetype(font_path, 26)
    text_font = ImageFont.truetype(font_path, 21)

    draw.text((30, 30), "会议纪要（无表格）", font=title_font, fill=(20, 20, 20))
    lines = [
        "本次会议讨论了下一季度的市场推广计划，",
        "确认由市场部牵头，技术部配合完成物料准备。",
        "下次会议定于下周三下午三点，地点在三号会议室。",
        "与会人员对预算方案没有异议。",
    ]
    y = 105
    for line in lines:
        draw.text((30, y), line, font=text_font, fill=(35, 35, 35))
        y += 42

    image = image.filter(ImageFilter.SMOOTH)
    path = out_dir / "meeting_notes_no_table.png"
    image.save(path)
    return path


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/in")
    out_dir.mkdir(parents=True, exist_ok=True)
    font = pick_font()
    if not font:
        print("警告：未找到中文字体，PDF 里的中文可能丢失")

    created = [
        make_invoice_pdf(out_dir, font),
        make_two_tables_pdf(out_dir, font),
        make_profile_pdf(out_dir, font),
        make_receipt_image(out_dir),
        make_table_screenshot(out_dir),
        make_plain_image(out_dir),
    ]
    for path in created:
        print("CREATED:", path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
