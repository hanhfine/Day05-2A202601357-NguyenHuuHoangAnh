# eval/traces/

Thư mục này chứa kết quả trace từ `run_eval.py --save-trace`.

**KHÔNG commit** các file trace vào repo — chúng chứa output của LLM và có thể lớn.
`.gitignore` đã chặn `eval/traces/*.json`.

Trace được dùng để:
- So sánh kết quả `mock` vs `real` (rubric R4)
- Debug khi một case fail bất ngờ
