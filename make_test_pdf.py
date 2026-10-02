"""Generate a simple English test.pdf used by read_pdf.py (needs fpdf2)."""
import sys
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    print("SKIP: fpdf2 not installed, cannot auto-generate test.pdf")
    sys.exit(2)

out = Path(sys.argv[1] if len(sys.argv) > 1 else "test.pdf")

PARAGRAPHS = [
    "DeepSeek Harness - PDF text extraction test",
    "This is a small sample document that contains several paragraphs of plain text.",
    "It exists so that read_pdf.py can prove that pdfplumber is able to pull text out of a real PDF file.",
    "Line three standing on its own.",
    "The quick brown fox jumps over the lazy dog. 0123456789 !@#$%^&*()",
    "Numbers and symbols: 3.14159, 42, 2024-01-01, hello@example.com",
    "Final paragraph: extraction finished successfully.",
]

pdf = FPDF()
pdf.set_title("DeepSeek Harness test PDF")
pdf.set_author("read_pdf.py setup")
pdf.add_page()
pdf.set_font("helvetica", size=16)
pdf.cell(0, 10, "Sample PDF for pdfplumber", new_x="LMARGIN", new_y="NEXT")
pdf.ln(4)
pdf.set_font("helvetica", size=12)
for para in PARAGRAPHS:
    pdf.multi_cell(0, 8, para, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

pdf.output(str(out))
print("CREATED:", out.resolve())
