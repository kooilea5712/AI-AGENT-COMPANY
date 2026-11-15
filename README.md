# Studio AI (bản thô)

Nhóm AI agent nhận job phần mềm, tự làm và bàn giao file; bạn chỉ duyệt ở hai điểm (brief, bàn giao).
Thiết kế đầy đủ: `docs/thiet-ke.md`. Phiên bản công cụ và model: `docs/moi-truong.md`.
Bằng chứng chạy thử đầu cuối: `docs/nghiem-thu/`.

## Chạy

Mỗi lệnh một cửa sổ PowerShell, từ thư mục gốc repo:

```powershell
.\scripts\start-omniroute.ps1   # tuỳ chọn, chỉ cần khi LLM_MODE=omniroute (bind loopback)
.\scripts\start-backend.ps1     # http://127.0.0.1:8000  (docs: /docs)
.\scripts\start-frontend.ps1    # http://127.0.0.1:5173
```

Test: `backend\.venv\Scripts\python -m pytest backend -q`

## Cấu hình (.env, mẫu ở .env.example)

- `LLM_MODE=direct`: gọi thẳng Ollama, ánh xạ combo -> model (`DIRECT_MODEL_*`). Dùng khi OmniRoute chưa có khoá cloud.
- `LLM_MODE=omniroute`: gửi tên combo (`brain/coder/fast/vision`) tới OmniRoute. **Trước khi dùng, nâng `requestQueue.maxWaitMs`
  (mặc định 15000) trong cài đặt resilience của OmniRoute**: model local nạp/sinh lâu hơn 15 giây sẽ bị cắt bằng lỗi 504.
- Khoá API cloud nhập trong dashboard OmniRoute, không ghi vào repo.

## Cấu trúc

```
backend/app/config.py        cấu hình từ .env
backend/app/llm/client.py    client OpenAI-compatible duy nhất
backend/app/agents/loop.py   vòng lặp agent bằng function calling (chịu model yếu)
backend/app/tools/sandbox.py 4 tool khoá trong jobs/<mã-job>/
backend/app/jobs/machine.py  máy trạng thái 8 bước, hai điểm dừng chờ người
backend/app/main.py          API FastAPI + SSE
prompts/*.md                 prompt từng vai, nạp lúc chạy (sửa file là có hiệu lực ngay)
jobs/<mã-job>/               brief.md plan.md log.md work/ deliverables/ ...
frontend/                    React + Vite + TypeScript
ollama/*.Modelfile           biến thể model với num_ctx 16384
```

`prompts/phu-*.md` là phụ lục do code thêm (giao thức đọc kết quả, môi trường Windows); các file còn lại lấy nguyên văn từ thiết kế.
Muốn thay vòng lặp bằng CrewAI/LangGraph: chỉ cần thay `agents/loop.py:run_agent` (cùng chữ ký) và giữ `machine.py`.

## Giới hạn của "sandbox" hiện tại (đọc kỹ)

Tool của agent chỉ là rào chắn mềm, KHÔNG phải sandbox thật:
- Chặn đường dẫn thoát khỏi `jobs/<mã-job>/` cho `read_file`/`write_file`/`list_dir` (có test).
- `run_command` chạy PowerShell với thư mục job làm thư mục hiện tại, timeout 60 giây, và từ chối lệnh khớp danh sách đen theo từ khoá
  (xoá đệ quy, curl/wget, pip/npm install, winget, shutdown…). Danh sách đen dễ bị lách.
- Lệnh chạy bằng quyền tài khoản của bạn. Script Python agent viết ra vẫn có thể đọc/ghi mọi nơi bạn có quyền, và có mạng.
  `cd ..` hay đường dẫn tuyệt đối trong chính lệnh không bị chặn (chỉ chuỗi `..\` bị từ chối).
- Hệ quả: chỉ chạy job bạn tin, đừng cho agent xử lý file/tài liệu lạ. Docker (chặng sau) mới cô lập thật.

## Đã biết / chưa làm

- Job `blocked`: bấm "Tiếp tục từ bước đã dừng" (kèm hướng dẫn nếu muốn); job quay lại đúng bước bị chặn, QA bị chặn thì quay về Thực thi với đủ 2 vòng sửa.
- Chỉ một task T1 mỗi job. Giám đốc chọn vai ở dòng đầu `plan.md` (`VAI: phần mềm` hoặc `VAI: media`). Media = logo/vector/ảnh; video và âm thanh chưa hỗ trợ.
- Agent dùng được `python` (venv backend, có Pillow), ffmpeg, magick, inkscape, và tool `describe_image` (model vision nhìn PNG/JPG).
  Model vision KHÔNG đo được kích thước/độ trong suốt (đã gặp: nó đoán sai); prompt bắt agent đo bằng `magick identify`/Pillow.
- Chất lượng thẩm mỹ của media còn yếu (xem `docs/nghiem-thu/logo-svg/`): QA chỉ kiểm được thứ đo được, mắt thẩm mỹ vẫn là bạn ở điểm duyệt bàn giao.
- Giám đốc chỉ được hỏi một lượt; lessons.md ở gốc repo được nạp vào prompt Giám đốc/Kỹ sư.
- Model local chạy tuần tự (một khoá trong `llm/client.py`).
