"""Dựng CV-mau-01.pdf để test đường upload PDF.  python data/cv-mau/make_pdf.py

Viết PDF bằng tay (~40 dòng) thay vì thêm reportlab/fpdf2: đây là fixture dùng một lần,
không đáng thêm dependency vào requirements của cả nhóm.

CHỮ KHÔNG DẤU LÀ CỐ Ý. Font Helvetica dựng sẵn trong PDF chỉ có WinAnsiEncoding, không
biểu diễn được "ộ" hay "ế". Và đây cũng là tình huống thật: rất nhiều CV PDF khi extract
ra bị mất dấu hoặc vỡ dấu. Nhờ vậy fixture này test được đúng chỗ đáng lo — regex mất dấu
là mù, còn đường LLM vẫn đọc được. Xem kết quả trong smoke_test.py.
"""
from pathlib import Path

D = Path(__file__).resolve().parent

DONG = [
    "CV MAU - HOAN TOAN BIA, dung de test chuc nang upload PDF.",
    "KHONG phai CV cua nguoi that.",
    "",
    "NGUYEN VAN A",
    "Email: nguyenvana.example@example.com",
    "Dien thoai: 0912 345 678",
    "GitHub: github.com/nguyenvana-example",
    "CCCD: 001234567890",
    "",
    "HOC VAN",
    "Dai hoc Bach Khoa - Sinh vien nam 3, nganh Cong nghe thong tin",
    "GPA: 3.42/4.0",
    "Hien dang o Ha Noi.",
    "",
    "KY NANG",
    "Python, SQL, pandas, Git, LLM API (OpenAI, Gemini), Docker co ban",
    "",
    "DU AN",
    "1. Chatbot hoi dap tai lieu hoc tap - dung LLM API + tim kiem theo doan.",
    "2. Dashboard phan tich diem hoc tap - SQL + Power BI.",
    "",
    "KHOA HOC",
    "AI Thuc Chien (Batch 03) - hoan thanh Day 1 den Day 5, track AI PM.",
]


def _esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def main() -> None:
    noi_dung = ("BT /F1 11 Tf 50 800 Td 14 TL\n"
                + "".join(f"({_esc(l)}) Tj T*\n" for l in DONG) + "ET")
    objs = [
        "<</Type/Catalog/Pages 2 0 R>>",
        "<</Type/Pages/Kids[3 0 R]/Count 1>>",
        "<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R"
        "/Resources<</Font<</F1 5 0 R>>>>>>",
        f"<</Length {len(noi_dung)}>>\nstream\n{noi_dung}\nendstream",
        "<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>",
    ]

    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, start=1):
        offs.append(len(out.encode("latin-1")))
        out += f"{i} 0 obj\n{o}\nendobj\n"

    xref_tai = len(out.encode("latin-1"))
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref_tai}\n%%EOF\n"

    f = D / "CV-mau-01.pdf"
    f.write_bytes(out.encode("latin-1"))
    print(f"{f.name}: {f.stat().st_size} bytes, {len(DONG)} dòng")


if __name__ == "__main__":
    main()
