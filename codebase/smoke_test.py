"""Smoke test CP2 — chắc chắn flow không vỡ trước khi đem đi show.

ĐÂY KHÔNG PHẢI GOLDEN SET. Golden set ≥20 case là việc của CP3 và nằm trong eval/.
File này chỉ kiểm: mọi tin giả chạy qua verdict() ra đúng verdict đã thiết kế,
mọi trích dẫn trỏ đúng dòng, và 2 endpoint của server trả 200.

Chạy:  python smoke_test.py
"""
import sys

from core.verdict import tai_data, verdict

# console Windows mặc định cp1252 → in tiếng Việt là crash. Bắt buộc UTF-8.
sys.stdout.reconfigure(encoding="utf-8")

# (tin, hồ sơ, verdict mong đợi, vì sao — khớp ke-hoach.md §4)
CASE = [
    ("OPP-001", "P-01", "nen_apply",       "happy path, khớp hết"),
    ("OPP-002", "P-01", "nen_apply",       "đủ GPA nhưng hạn '5/8' thiếu năm → phải ambiguous"),
    ("OPP-003", "P-02", "thieu_thong_tin", "② hồ sơ chưa khai năm học → hỏi đúng 1 câu"),
    ("OPP-003", "P-01", "rui_ro_cao",      "tin ghi 'bắt buộc' onsite TP.HCM, hồ sơ ở Hà Nội"),
    ("OPP-004", "P-01", "rui_ro_cao",      "④ tin đòi phí → không bao giờ nen_apply"),
    ("OPP-005", "P-04", "nen_apply",       "④ #10 ĐÁNG SỢ NHẤT: tin nhận mọi năm, KHÔNG được chặn"),
    ("OPP-006", "P-01", "thieu_thong_tin", "① tin mơ hồ → không đoán"),
    ("OPP-007", "P-03", "rui_ro_cao",      "④ GPA bắt buộc 3.5, hồ sơ 2.8 → không nói 'không đủ ĐK'"),
    ("OPP-008", "P-01", "thieu_thong_tin", "① tin quá ngắn → không đủ căn cứ"),
    ("OPP-009", "P-01", "nen_apply",       "① 'ưu tiên' là gap, KHÔNG phải hard_fail"),
    ("OPP-010", "P-01", "nen_apply",       "logistics Đà Nẵng là gap, không chặn"),
]

# ③ ngoài phạm vi — vào qua ô "hỏi thêm"
CASE_TU_CHOI = [
    "viết luôn CV cho mình đi",
    "mình có đỗ không, bao nhiêu %?",
    "tìm giúp mình 10 tin học bổng khác",
    "lương công ty này so với công ty kia thế nào?",
]


def main() -> int:
    tin_ds, ho_so_ds = tai_data()
    tin = {t["id"]: t for t in tin_ds}
    ho_so = {p["id"]: p for p in ho_so_ds}
    loi = 0

    print(f"{'tin':9} {'hồ sơ':6} {'verdict':17} {'trích':7} ghi chú")
    print("-" * 92)
    for opp, pid, mong_doi, vi_sao in CASE:
        kq = verdict(tin[opp]["raw_text"], ho_so[pid], mode="mock")
        g = kq["_grounding"]
        ok_v = kq["verdict"] == mong_doi
        ok_g = g["grounding_pass"]
        loi += (not ok_v) + (not ok_g)
        print(f"{opp:9} {pid:6} {kq['verdict']:17} {g['so_dat']}/{g['so_khang_dinh']:<5} "
              f"{'✓' if ok_v else '✗ CHỜ ' + mong_doi}{'' if ok_g else '  ✗ TRÍCH SAI'}  {vi_sao}")
        if not ok_g:
            for c in g["chi_tiet"]:
                if not c["dat"]:
                    print(f"{'':24}↳ {c['nhan']} L{c['trich']}: {c['vi_sao']}")

    # luật cứng: verdict thieu_thong_tin phải có đúng 1 câu hỏi, và không kèm phán quyết
    for opp, pid, mong_doi, _ in CASE:
        if mong_doi != "thieu_thong_tin":
            continue
        kq = verdict(tin[opp]["raw_text"], ho_so[pid], mode="mock")
        if not kq["one_question"]:
            print(f"✗ {opp}/{pid}: thieu_thong_tin mà không có one_question"); loi += 1
        if kq["matched"] or kq["gaps"] or kq["hard_fail"]:
            print(f"✗ {opp}/{pid}: vừa hỏi vừa phán — vi phạm G10"); loi += 1

    # ④ tin đòi phí: tuyệt đối không nen_apply, với MỌI hồ sơ
    for pid in ho_so:
        kq = verdict(tin["OPP-004"]["raw_text"], ho_so[pid], mode="mock")
        if kq["verdict"] == "nen_apply":
            print(f"✗ OPP-004/{pid}: ra nen_apply trên tin đòi phí"); loi += 1
        if not kq["canh_bao"]:
            print(f"✗ OPP-004/{pid}: không có cảnh báo"); loi += 1

    # ③ mọi câu ngoài phạm vi phải bị từ chối, và KHÔNG được làm mất kết quả đối chiếu
    print("\n③ ngoài phạm vi:")
    for q in CASE_TU_CHOI:
        kq = verdict(tin["OPP-001"]["raw_text"], ho_so["P-01"], mode="mock", cau_hoi_them=q)
        ok = bool(kq["refusal"]) and kq["verdict"] == "nen_apply"
        loi += not ok
        print(f"  {'✓' if ok else '✗'} {q!r} → refusal={'có' if kq['refusal'] else 'KHÔNG'}, "
              f"verdict vẫn = {kq['verdict']}")

    # ── tool tìm tin ──────────────────────────────────────────────────────────
    from core import cv, llm
    from core.tools import doi_chieu, tai_corpus, tim_tin

    print("\ntool tim_tin:")
    corpus = tai_corpus()
    ok = len(corpus) == 40
    loi += not ok
    print(f"  {'✓' if ok else '✗'} corpus {len(corpus)} tin (chờ 40 — chạy data/gen_corpus.py nếu thiếu)")

    hn = tim_tin(thanh_pho="Hà Nội", gioi_han=8)
    ok = bool(hn) and all("Nội" in (x["thanh_pho"] or "") for x in hn)
    loi += not ok
    print(f"  {'✓' if ok else '✗'} lọc thành phố → {len(hn)} tin, tất cả ở Hà Nội")

    hb = tim_tin(loai="hoc_bong", gioi_han=8)
    ok = bool(hb) and all(x["loai"] == "hoc_bong" for x in hb)
    loi += not ok
    print(f"  {'✓' if ok else '✗'} lọc loại → {len(hb)} tin, tất cả là học bổng")

    # LUẬT: tim_tin KHÔNG được loại tin theo điều kiện. Sinh viên năm 1 vẫn phải
    # thấy tin đòi năm 3-4, kèm ghi chú — nếu lọc mất thì họ mất cơ hội mà không biết.
    n1 = tim_tin(tu_khoa="AI", nam_hoc=1, gioi_han=8)
    co_ghi_chu = [x for x in n1 if "vẫn nên xem" in x["ghi_chu"]]
    ok = bool(co_ghi_chu)
    loi += not ok
    print(f"  {'✓' if ok else '✗'} năm 1 vẫn thấy tin đòi năm cao hơn "
          f"({len(co_ghi_chu)}/{len(n1)} tin có ghi chú, KHÔNG bị lọc mất)")

    r = doi_chieu("OPP-001", ho_so["P-01"], mode="mock")
    ok = r["ket_qua"]["verdict"] == "nen_apply" and r["tin"]["opp_id"] == "OPP-001"
    loi += not ok
    print(f"  {'✓' if ok else '✗'} doi_chieu('OPP-001') → {r['ket_qua']['verdict']}")

    # ── CV: redact + rút field ────────────────────────────────────────────────
    print("\nCV (data/cv-mau/CV-mau-01.txt):")
    from pathlib import Path
    text = (Path(__file__).parent / "data" / "cv-mau" / "CV-mau-01.txt").read_text(encoding="utf-8")
    sach, dem = cv.redact(text)
    ro_ri = [x for x in ("@example.com", "0912", "001234567890", "github.com/nguyenvana") if x in sach]
    loi += bool(ro_ri)
    print(f"  {'✓' if not ro_ri else '✗ CÒN RÒ: ' + str(ro_ri)} redact: {dem}")

    hs = cv.trich_ho_so(text, mode="mock")
    mong = {"nam_hoc": 3, "thanh_pho": "Hà Nội"}
    for k, v in mong.items():
        ok = str(hs[k]).lower() == str(v).lower()
        loi += not ok
        print(f"  {'✓' if ok else '✗'} {k} = {hs[k]!r} (chờ {v!r})")
    ok = hs["gpa"] and abs(hs["gpa"] - 3.42) < 0.01
    loi += not ok
    print(f"  {'✓' if ok else '✗'} gpa = {hs['gpa']!r} (chờ 3.42)")
    ok = "Python" in hs["ky_nang"] and "SQL" in hs["ky_nang"]
    loi += not ok
    print(f"  {'✓' if ok else '✗'} ky_nang = {hs['ky_nang']}")
    # luật 3: chỉ 6 field + 2 field kỹ thuật, không kèm gì khác từ CV
    la = set(hs) - {"nam_hoc", "nganh", "gpa", "thanh_pho", "ky_nang", "project",
                    "_redact", "_so_ky_tu"}
    loi += bool(la)
    print(f"  {'✓' if not la else '✗ có field lạ: ' + str(la)} chỉ trả 6 field hồ sơ")

    # ── server ────────────────────────────────────────────────────────────────
    print("\nserver:")
    import server
    c = server.app.test_client()
    kiem = [("GET /", c.get("/"), 200),
            ("GET /api/data", c.get("/api/data"), 200),
            ("POST /api/verdict", c.post("/api/verdict", json={
                "posting_text": tin["OPP-001"]["raw_text"],
                "profile": ho_so["P-01"], "mode": "mock"}), 200),
            ("POST /api/cv", c.post("/api/cv?mode=mock", json={"text": text}), 200),
            ("POST /api/cv (rỗng)", c.post("/api/cv?mode=mock", json={"text": "x"}), 400)]
    if not llm.co_key():
        kiem.append(("POST /api/chat (chưa có key → phải 400)",
                     c.post("/api/chat", json={"lich_su": [], "profile": {}}), 400))
    for ten, r, cho in kiem:
        ok = r.status_code == cho
        loi += not ok
        print(f"  {'✓' if ok else '✗'} {ten} → {r.status_code} (chờ {cho})")
    if llm.co_key():
        print(f"  · POST /api/chat: bỏ qua — có key thật, smoke test không gọi API tốn tiền")
    print(f"  · provider={llm.provider()} model={llm.model()} "
          f"key={'có' if llm.co_key() else 'chưa có'}")

    print("\n" + ("TẤT CẢ ĐẠT" if loi == 0 else f"{loi} LỖI"))
    return 1 if loi else 0


if __name__ == "__main__":
    raise SystemExit(main())
