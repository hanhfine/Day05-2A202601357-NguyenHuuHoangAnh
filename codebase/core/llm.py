"""Lớp gọi LLM — chỗ DUY NHẤT trong codebase biết provider là ai.

Mọi thứ khác (verdict, agent, cv) gọi qua đây, nên đổi provider là đổi 1 biến môi trường.

    OPPM_PROVIDER = openai (mặc định) | gemini
    OPPM_MODEL    = tên model, mặc định gpt-4o-mini / gemini-3-flash
    OPENAI_API_KEY hoặc GEMINI_API_KEY

Dùng `requests` trực tiếp thay vì SDK: máy nào cũng đã có requests, không thêm rủi ro
`pip install` giữa hackathon.

temperature = 0 ở mọi lời gọi — golden set phải chạy lại ra cùng kết quả.
"""
import json
import os
import re
import time
from pathlib import Path

CODEBASE = Path(__file__).resolve().parent.parent
REPO = CODEBASE.parent

MAC_DINH = {"openai": "gpt-4o-mini", "gemini": "gemini-3-flash"}
URL_OPENAI = "https://api.openai.com/v1/chat/completions"
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"


def _nap_env() -> None:
    """Đọc file .env vào os.environ. Biến môi trường thật LUÔN thắng file.

    Tự viết 12 dòng thay vì thêm python-dotenv: bớt một thứ có thể `pip install` lỗi
    giữa hackathon, và ai cũng đọc hiểu được (vibe-coding rule). Dòng trống, dòng #,
    và giá trị rỗng đều bị bỏ qua — nên `.env` mới tải về chưa điền key thì app vẫn
    báo "chưa có key" đúng, không phải lỗi 401 khó hiểu.
    """
    for f in (CODEBASE / ".env", REPO / ".env"):
        if not f.exists():
            continue
        for dong in f.read_text(encoding="utf-8").splitlines():
            dong = dong.strip()
            if not dong or dong.startswith("#") or "=" not in dong:
                continue
            ten, _, gia = dong.partition("=")
            ten, gia = ten.strip(), gia.strip().strip('"').strip("'")
            if gia and not os.environ.get(ten):
                os.environ[ten] = gia


_nap_env()


def provider() -> str:
    return (os.environ.get("OPPM_PROVIDER") or "openai").lower()


def model() -> str:
    return os.environ.get("OPPM_MODEL") or MAC_DINH.get(provider(), "gpt-4o-mini")


def _key() -> str:
    p = provider()
    ten = "OPENAI_API_KEY" if p == "openai" else "GEMINI_API_KEY"
    k = os.environ.get(ten)
    if not k:
        raise RuntimeError(
            f"Chưa có {ten}. Đặt biến môi trường rồi chạy lại:\n"
            f"  PowerShell:  $env:{ten} = '...'\n"
            "TUYỆT ĐỐI không viết key vào file trong repo — repo này đang public.")
    return k


def co_key() -> bool:
    ten = "OPENAI_API_KEY" if provider() == "openai" else "GEMINI_API_KEY"
    return bool(os.environ.get(ten))


def _ghi_trace(nhan: str, req: dict, resp: dict) -> None:
    """Rubric R5 đòi log/trace lời gọi AI thật trong repo."""
    d = REPO / "eval" / "traces"
    d.mkdir(parents=True, exist_ok=True)
    ten = f"{time.strftime('%Y%m%d-%H%M%S')}-{nhan}-{model()}.json"
    (d / ten).write_text(
        json.dumps({"provider": provider(), "model": model(),
                    "request": req, "response": resp}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def _post(url: str, **kw) -> dict:
    import requests
    r = requests.post(url, timeout=90, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{provider()} trả {r.status_code}: {r.text[:400]}")
    return r.json()


def json_call(system: str, user: str, nhan: str = "json") -> dict:
    """Một lời gọi ép trả JSON. Dùng cho verdict(real) và đọc CV."""
    if provider() == "gemini":
        req = {"contents": [{"role": "user", "parts": [{"text": user}]}],
               "systemInstruction": {"parts": [{"text": system}]},
               "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
        data = _post(URL_GEMINI.format(m=model()), params={"key": _key()}, json=req)
        txt = data["candidates"][0]["content"]["parts"][0]["text"]
    else:
        req = {"model": model(), "temperature": 0,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
        data = _post(URL_OPENAI, headers={"Authorization": f"Bearer {_key()}"}, json=req)
        txt = data["choices"][0]["message"]["content"]
    _ghi_trace(nhan, req, data)
    txt = re.sub(r"^```(?:json)?|```$", "", (txt or "").strip(), flags=re.M).strip()
    return json.loads(txt)


def chat_raw(messages: list, tools: list) -> dict:
    """Một lượt chat có tool-calling. Trả về message của assistant (có thể chứa tool_calls).

    Chỉ OpenAI — Gemini dùng schema tool khác, không làm hai đường trong 1,5 ngày.
    """
    if provider() != "openai":
        raise RuntimeError("Chat có tool hiện chỉ chạy với OPPM_PROVIDER=openai. "
                           "Ô đối chiếu trực tiếp vẫn dùng được với gemini.")
    req = {"model": model(), "temperature": 0, "messages": messages,
           "tools": tools, "tool_choice": "auto"}
    data = _post(URL_OPENAI, headers={"Authorization": f"Bearer {_key()}"}, json=req)
    _ghi_trace("chat", req, data)
    return data["choices"][0]["message"]
