# Môi trường (ghi ngày 2026-11-15)

Máy: Windows 11 Pro 10.0.26200, i5-14400F, 32 GB RAM, RTX 5070 12 GB (driver 617.14). Shell: PowerShell 5.1, trình quản lý gói: winget 1.29.

| Mục | Phiên bản | Ghi chú |
| --- | --- | --- |
| Git | 2.55.0 | có sẵn |
| Python | 3.14.7 (qua `py`) | lệnh `python` trong PATH chỉ là shortcut Microsoft Store; dùng `py` hoặc venv `backend\.venv` |
| Node.js | 24.21.0, npm 11.19.0 | có sẵn |
| Ollama | 0.34.2 | có sẵn; có bản mới 0.40.16 chưa cập nhật (không đụng) |
| OmniRoute | 3.8.50 (npm toàn cục) | có sẵn, dữ liệu ở `~\.omniroute`; đã sao lưu trước khi sửa |
| FFmpeg / ffprobe | 9.0.2 (Gyan.FFmpeg, winget) | cài mới |
| ImageMagick | 7.1.2-34 Q16-HDRI (winget) | cài mới |
| Inkscape | 1.4.4 (winget) | cài mới, `C:\Program Files\Inkscape\bin` không nằm trong PATH |

## Model Ollama

| Tag | Dung lượng | Dùng cho | Thử tool call thật |
| --- | --- | --- | --- |
| gemma4:12b | 8.0 GB | `brain`, `coder`, `vision` | ĐẠT: tool call đúng chuẩn, ghi file + chạy lệnh trong 3 bước |
| qwen3:4b | 2.5 GB | `fast` | ĐẠT: đúng chuẩn, 2 bước |
| qwen2.5-coder:14b | 9.0 GB | không dùng | KHÔNG ĐẠT: trả tool call dạng JSON trong content (không dùng `tool_calls`), và gọi lặp cùng một call 8 lần vì không đọc kết quả tool. Giữ lại trên đĩa, có thể xoá bằng `ollama rm` |
| gemma4:latest | 9.6 GB | không dùng | có sẵn từ trước |

Cách thử: `backend\.venv\Scripts\python scripts\probe_tools.py <tag>...`

## OmniRoute

- Nhà cung cấp đã có sẵn từ trước: `cloudflare-ai`, `llm7`. Đã thêm `ollama-local` (không cần khoá).
- Bốn combo `brain`, `coder`, `vision` (→ `ollama-local/gemma4:12b`) và `fast` (→ `ollama-local/qwen3:4b`), chiến lược `priority`. Hiện **chỉ có Ollama**; bạn thêm các nhà cung cấp cloud lên trước trong dashboard (http://localhost:20128) để Ollama đứng cuối.
- Mặc định OmniRoute nghe trên `0.0.0.0` không cần khoá. Đã khởi động lại với `OMNIROUTE_SERVER_HOST=127.0.0.1`; dùng `scripts\start-omniroute.ps1` để giữ như vậy.
