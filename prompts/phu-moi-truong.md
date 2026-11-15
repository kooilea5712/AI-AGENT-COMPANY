[PHỤ LỤC CỦA CODE, không nằm trong docs/thiet-ke.md]
Môi trường chạy: Windows 11, PowerShell. Thư mục hiện tại của mọi lệnh là thư mục job. Dùng đường dẫn tương đối (work/..., deliverables/...).
Python chạy bằng `py` (không phải `python`). Không có kết nối cài thêm thư viện: chỉ dùng thư viện chuẩn của Python trừ khi brief nói khác (pip install bị chặn).
Công cụ bạn có: read_file, write_file, list_dir, run_command. Gọi công cụ bằng cơ chế tool call, không viết JSON vào câu trả lời.
Khi xong việc, trả lời bằng văn bản thường (không gọi công cụ nữa).
