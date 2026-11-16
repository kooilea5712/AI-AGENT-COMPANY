# Chạy thử luồng mới (2026-11-16), toàn bộ bằng model local

Job: "script tính tổng các số nguyên trong file văn bản". Không có khoá Claude nên cả đội chạy bằng model dự phòng (`studio-gemma4-12b`; Kiểm thử viên `studio-qwen3-4b`).

Đã chạy thật và thấy trong `log.md`:
- Giám đốc viết brief, **tự duyệt brief** (không dừng chờ chủ), lập `plan.json` hợp lệ (1 task, Kỹ sư phần mềm), commit sau từng bước (dòng `git`).
- Kỹ sư làm xong task, báo cáo, commit. Kiểm định viết 10 testcase (`testcases.json`) từ bản chụp sản phẩm.
- Kiểm thử viên chạy từng testcase một lượt gọi riêng; code chạy lại độc lập các case có `expect` trong sandbox Docker (bản sao dùng một lần).
- Phát hiện testcase hỏng ở bước setup -> trả Kiểm định sửa (2 lần) thay vì đổ lỗi cho Kỹ sư.
- Backend khởi động lại giữa chừng thì job tự tiếp tục; chủ bấm "Dừng job" thì job dừng (blocked) và vẫn tiếp tục được.

Chưa tới được bàn giao: model local nhỏ làm Kiểm định/Kiểm thử chậm (vài phút mỗi case) và viết testcase sai (ví dụ gọi `python sum_integers.py` trong khi file nằm ở `deliverables/`).
Đây là lý do mặc định dùng Claude Sonnet/Haiku cho hai vai này khi có khoá. Phần Claude API chưa được thử với khoá thật.
