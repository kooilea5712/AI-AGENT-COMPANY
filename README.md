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

## Sandbox

`SANDBOX_MODE=docker` (mặc định trong `.env`): mỗi lệnh của agent chạy trong một container dùng một lần từ image `studio-sandbox`
(Debian + Python 3.12 + Pillow + ffmpeg + ImageMagick 7 + Inkscape + git):
`--network none`, 2 GB RAM, 2 CPU, tối đa 256 tiến trình, bỏ hết capability, chỉ mount thư mục `jobs/<mã-job>/` tại `/job`.
Hết thời gian thì `docker kill` đúng container. Có 6 test Docker thật (`backend/tests/test_docker_sandbox.py`: không thấy file host,
không mạng, `rm -rf /` không ảnh hưởng host, timeout dọn container).

Dựng image một lần (khoảng 1,3 GB): `docker build -t studio-sandbox docker/sandbox`. Cần Docker Desktop đang chạy.
Lệnh trong container là bash/Linux; prompt môi trường tự đổi theo chế độ (`prompts/phu-moi-truong-docker.md`).

Còn lại cần biết:
- `read_file`/`write_file`/`list_dir` chạy trên host, chặn thoát khỏi thư mục job (có test). Container không phải ranh giới bảo mật tuyệt đối
  (chung kernel với VM của Docker), nhưng đủ cho agent chạy script không đáng tin trên máy cá nhân.
- Giờ trong container là UTC: tên file đặt theo ngày sửa file (không có EXIF) sẽ lệch múi giờ so với giờ máy bạn.
- `SANDBOX_MODE=local` (khi chưa có Docker) chỉ là PowerShell + danh sách đen từ khoá, KHÔNG cô lập: script agent viết ra làm được mọi thứ bạn làm được.

## Đã biết / chưa làm

- Job `blocked`: bấm "Tiếp tục từ bước đã dừng" (kèm hướng dẫn nếu muốn); job quay lại đúng bước bị chặn, QA bị chặn thì quay về Thực thi với đủ 2 vòng sửa.
- Chỉ một task T1 mỗi job. Giám đốc chọn vai ở dòng đầu `plan.md` (`VAI: phần mềm` hoặc `VAI: media`). Media = logo/vector/ảnh; video và âm thanh chưa hỗ trợ.
- Agent dùng được `python` (venv backend, có Pillow), ffmpeg, magick, inkscape, và tool `describe_image` (model vision nhìn PNG/JPG).
  Model vision KHÔNG đo được kích thước/độ trong suốt (đã gặp: nó đoán sai); prompt bắt agent đo bằng `magick identify`/Pillow.
- Chất lượng thẩm mỹ của media còn yếu (xem `docs/nghiem-thu/logo-svg/`): QA chỉ kiểm được thứ đo được, mắt thẩm mỹ vẫn là bạn ở điểm duyệt bàn giao.
- Giám đốc chỉ được hỏi một lượt; lessons.md ở gốc repo được nạp vào prompt Giám đốc/Kỹ sư.
- Model local chạy tuần tự (một khoá trong `llm/client.py`).
