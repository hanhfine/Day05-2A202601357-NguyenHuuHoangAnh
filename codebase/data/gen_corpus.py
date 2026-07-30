"""Sinh corpus 40 tin giả = 10 tin chỗ khó gõ tay (postings.json) + 30 tin thường sinh tự động.

Phương pháp sinh ghi ở đây để người ngoài nhóm chạy lại ra ĐÚNG cùng 40 tin
(seed cố định) — rubric đòi "phương pháp kiểm lại được".

    python data/gen_corpus.py     →  data/corpus.json

Toàn bộ tên tổ chức là tên BỊA. Không có tin tuyển dụng thật nào trong file này.
"""
import json
import random
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
random.seed(42)
sys.stdout.reconfigure(encoding="utf-8")   # console Windows là cp1252

TC_THUCTAP = ["Sao Mai Tech", "Minh Long Group", "Đại Tín", "Hoa Sen Digital",
              "Bách Thảo Labs", "An Khang Data", "Vạn Xuân AI", "Trúc Bạch Soft",
              "Nam Phong Analytics", "Lam Sơn Robotics", "Hồng Hà Fintech", "Tân Việt Cloud"]
TC_HOCBONG = ["Quỹ Khuyến học Trí Việt", "Viện Nghiên cứu Bách Khoa", "Quỹ Sông Hồng",
              "Quỹ Đổi mới Hoa Sen", "Học viện Nam Phong", "Quỹ Tài năng Lam Sơn"]
VAI = [("AI Engineer", "Python, hiểu cách gọi LLM API"), ("Data Analyst", "SQL, Excel"),
       ("Machine Learning", "Python, pandas"), ("Data Engineer", "SQL, Python"),
       ("AI Product Analyst", "SQL, viết tài liệu"), ("Computer Vision", "Python, OpenCV"),
       ("NLP", "Python, hiểu embedding"), ("MLOps", "Python, Docker")]
NGANH = ["CNTT", "CNTT, Toán tin", "CNTT, Khoa học dữ liệu", "CNTT, Điện tử",
         "Khoa học dữ liệu, Toán tin"]
NOI = ["Hà Nội", "TP.HCM", "Đà Nẵng"]
NAM = ["năm 3 hoặc năm 4", "năm 3-4", "năm 2 trở lên", "năm 3 trở lên", "năm 2, 3, 4"]
GPA = [None, "2.8", "3.0", "3.2", "3.5"]
GIAY_TO = ["CV", "CV + portfolio", "CV + bảng điểm", "bảng điểm, thư giới thiệu",
           "CV + link 1 project"]


def tin_thuc_tap(i: int) -> dict:
    vai, ky_nang = random.choice(VAI)
    tc, noi, nam, gpa = (random.choice(TC_THUCTAP), random.choice(NOI),
                         random.choice(NAM), random.choice(GPA))
    online = random.random() < 0.25
    d = random.randint(1, 28)
    dong = [f"[Thực tập sinh {vai} — {tc}]",
            f"Tuyển {random.randint(1, 4)} thực tập sinh cho quý 4/2026.",
            "Yêu cầu:",
            f"- Sinh viên {nam} ngành {random.choice(NGANH)}",
            f"- {ky_nang}"]
    if gpa:
        dong.append(f"- GPA từ {gpa}/4.0 trở lên")
    if random.random() < 0.4:
        dong.append(f"- Ưu tiên ứng viên đã từng làm project liên quan {vai}")
    dong.append("Hình thức: online toàn thời gian." if online
                else f"- Cam kết {random.randint(2, 4)} buổi/tuần tại văn phòng {noi}")
    dong.append(f"Hồ sơ: {random.choice(GIAY_TO)}.")
    dong.append(f"Hạn nhận hồ sơ: {d:02d}/0{random.choice([8, 9])}/2026.")
    return {"id": f"OPP-{i:03d}", "kind": "thuc_tap",
            "title": f"Thực tập sinh {vai} — {tc}",
            "_muc_tieu": "case thường (sinh tự động, seed=42)",
            "raw_text": "\n".join(dong)}


def tin_hoc_bong(i: int) -> dict:
    tc, nam, gpa = random.choice(TC_HOCBONG), random.choice(NAM), random.choice(GPA[2:])
    d = random.randint(1, 28)
    dong = [f"[Học bổng {random.choice(['Khuyến học', 'Tài năng', 'Hỗ trợ học tập'])} "
            f"{random.randint(2026, 2027)} — {tc}]",
            f"Dành cho sinh viên {nam} ngành {random.choice(NGANH)}.",
            f"Điều kiện: GPA từ {gpa}/4.0.",
            f"Giá trị: {random.choice([5, 10, 15, 20])}.000.000 VNĐ/suất, "
            f"{random.randint(5, 30)} suất.",
            f"Yêu cầu hồ sơ: {random.choice(GIAY_TO)}.",
            f"Hạn nộp: {d:02d}/0{random.choice([8, 9])}/2026."]
    if random.random() < 0.3:
        dong.insert(-1, f"Lưu ý: chỉ nhận hồ sơ bản cứng tại văn phòng {random.choice(NOI)}.")
    return {"id": f"OPP-{i:03d}", "kind": "hoc_bong",
            "title": dong[0].strip("[]"),
            "_muc_tieu": "case thường (sinh tự động, seed=42)",
            "raw_text": "\n".join(dong)}


def main() -> None:
    goc = json.loads((D / "postings.json").read_text(encoding="utf-8"))["postings"]
    them = [(tin_thuc_tap if n % 3 else tin_hoc_bong)(n) for n in range(11, 41)]
    out = {
        "_ghi_chu": "DATA GIẢ TỰ SINH. OPP-001..010 gõ tay, mỗi tin bắn vào 1 lớp chỗ khó "
                    "(xem postings.json). OPP-011..040 sinh bằng gen_corpus.py với seed=42 "
                    "— chạy lại script ra đúng cùng 30 tin. Mọi tên tổ chức là tên bịa.",
        "postings": goc + them,
    }
    (D / "corpus.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    print(f"corpus.json: {len(out['postings'])} tin "
          f"({len(goc)} gõ tay + {len(them)} sinh tự động)")
    print("  thực tập:", sum(1 for t in out["postings"] if t["kind"] == "thuc_tap"),
          "· học bổng:", sum(1 for t in out["postings"] if t["kind"] == "hoc_bong"))


if __name__ == "__main__":
    main()
