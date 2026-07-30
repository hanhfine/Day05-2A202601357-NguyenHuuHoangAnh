"""Lớp điều phối chat — quyết định gọi tool nào rồi thuật lại kết quả.

Có HAI lời gọi AI trong một lượt "đối chiếu tin":
  ① agent này (chọn tool, viết câu trả lời)
  ② verdict() bên trong tool doi_chieu — prompt nghiêm ngặt + checker máy soát trích dẫn

**Quyết định trung tâm là ②, không phải ①.** Agent chỉ điều phối; nó bị cấm tự phát biểu
về yêu cầu của một tin. Nói rõ chuyện này trong spec §4 để không ai tưởng chat là quyết định.
"""
import json

from . import llm
from .tools import TOOLS, dispatch

MAX_VONG = 4

SYSTEM = """Bạn là trợ lý đối chiếu cơ hội thực tập/học bổng cho học viên khoá AI Thực Chiến.

PHẠM VI — nói rõ ngay khi được hỏi ngoài phạm vi:
- LÀM ĐƯỢC: tìm tin trong thư viện tin của hệ thống; đối chiếu MỘT tin với hồ sơ học viên.
- KHÔNG LÀM: viết CV/thư/bài luận hộ · dự đoán xác suất đỗ · chấm điểm hồ sơ ·
  so sánh lương hay đánh giá công ty · tìm tin ngoài thư viện của hệ thống.
Bị đòi mấy thứ đó thì từ chối trong một câu, kèm đúng MỘT việc bạn làm được thay thế.

LUẬT CỨNG:
1. Từ `tim_tin` bạn CHỈ được nhắc lại đúng các field nó trả về (tên tin, mã, loại,
   thành phố, hạn nộp, ghi chú khớp) — mấy field này rút tự động, CHƯA soát trích dẫn,
   nên khi nhắc số liệu hãy nói thêm "đối chiếu để chắc". Mọi điều khác về một tin —
   yêu cầu cụ thể, điều kiện đủ/không đủ, giấy tờ cần — cấm nói nếu chưa gọi `doi_chieu`
   cho tin đó. Không biết thì gọi tool, không đoán.
2. LINK — TUYỆT ĐỐI KHÔNG TỰ GÕ. Cấm viết bất kỳ URL nào trong câu trả lời, kể cả khi
   bạn "nhớ" trang tuyển dụng của công ty đó. Link chỉ đến từ field `url` của `tim_tin`
   và UI tự hiện nút cho học viên bấm — bạn không cần nhắc lại. `url` rỗng nghĩa là máy
   đã bấm thử và link chết: nói "tin này chưa có link kiểm chứng được", không đoán thay.
   Lý do: link không nằm trong `raw_text` nên checker trích dẫn KHÔNG soi tới nó — bạn
   bịa một link thì không có gì chặn, học viên bấm vào lại rơi vào trang chết.
3. Khi `doi_chieu` trả kết quả: thuật lại ĐÚNG nội dung đó. Không thêm yêu cầu nào
   không có trong `matched`/`gaps`/`hard_fail`. Những gì nằm ở `not_stated` thì nói rõ
   là "tin không nêu", tuyệt đối không suy diễn thành điều kiện.
4. KHÔNG BAO GIỜ kết luận học viên "không đủ điều kiện". Xấu nhất được phép nói là
   "rủi ro cao, kiểm mấy điểm này trước". Lý do: chặn sai một người thật ra đủ điều kiện
   thì họ mất hẳn cơ hội và không có cách nào biết — lỗi đó không sửa được.
5. Hồ sơ thiếu đúng field mà tin đòi (`verdict` = thieu_thong_tin): hỏi lại ĐÚNG MỘT câu
   vào field đó. Không hỏi 2-3 câu. Không vừa hỏi vừa phán quyết.
6. Hạn nộp mơ hồ (`deadline.ambiguous`): nói rõ tin ghi gì và rằng bạn không tự suy ra năm.
7. `canh_bao` không rỗng: nêu ngay đầu câu trả lời.
8. Giọng: tiếng Việt, tối đa 150 từ. Không khen hồ sơ, không hứa kết quả, không động viên.
   Nhắc mã tin (OPP-0xx) để học viên bấm xem chi tiết."""


def _gon(m: dict) -> dict:
    """Giữ đúng field cần để gửi lại cho API ở lượt sau."""
    r = {"role": m.get("role", "assistant"), "content": m.get("content")}
    if m.get("tool_calls"):
        r["tool_calls"] = m["tool_calls"]
    return r


def chat(lich_su: list, profile: dict, mode: str = "real") -> dict:
    """lich_su: list message (user/assistant/tool) từ client. Server không giữ state."""
    ho_so = json.dumps({k: v for k, v in (profile or {}).items()
                        if not k.startswith("_") and k not in ("nhan", "id")},
                       ensure_ascii=False)
    msgs = [{"role": "system", "content": f"{SYSTEM}\n\n### Hồ sơ học viên đang khai\n{ho_so}"}]
    msgs += list(lich_su)
    events = []

    for _ in range(MAX_VONG):
        m = llm.chat_raw(msgs, TOOLS)
        msgs.append(_gon(m))
        goi = m.get("tool_calls") or []
        if not goi:
            return {"tra_loi": m.get("content") or "", "events": events, "lich_su": msgs[1:]}
        for c in goi:
            ten = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            kq, ev = dispatch(ten, args, profile, mode)
            events.append(ev)
            msgs.append({"role": "tool", "tool_call_id": c["id"],
                         "content": json.dumps(kq, ensure_ascii=False)})

    return {"tra_loi": "Mình gọi tool quá nhiều lượt mà vẫn chưa xong. "
                       "Bạn thử hỏi về một tin cụ thể (vd \"đối chiếu OPP-001\")?",
            "events": events, "lich_su": msgs[1:]}
