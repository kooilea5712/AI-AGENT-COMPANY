# Studio AI (bản thô)

Nhóm AI agent nhận job phần mềm, tự làm và bàn giao file; bạn chỉ duyệt ở hai điểm (brief, bàn giao).
Thiết kế đầy đủ: `docs/thiet-ke.md`. Phiên bản công cụ và model: `docs/moi-truong.md`.
Bằng chứng chạy thử đầu cuối: `docs/nghiem-thu/`.

## Chạy

**Cách chính: mở `Studio AI.exe`** (xem "Đóng gói exe" bên dưới). Nó tự bật Docker Desktop (nếu có), Ollama, OmniRoute (chỉ loopback) và
backend, đợi sẵn sàng rồi mở giao diện trong cửa sổ riêng. Đóng cửa sổ thì nó tắt đúng những dịch vụ nó đã bật; dịch vụ chạy sẵn từ trước
thì để nguyên. Nhật ký của launcher: `%APPDATA%\Studio AI\logs\` (launcher.log, backend.log).

Chạy tay (để phát triển), mỗi lệnh một cửa sổ PowerShell, từ thư mục gốc repo:

```powershell
.\scripts\start-omniroute.ps1   # chỉ cần khi LLM_MODE=omniroute (bind loopback)
.\scripts\start-backend.ps1     # http://127.0.0.1:8000, đồng thời phục vụ giao diện build sẵn (frontend/dist)
.\scripts\start-frontend.ps1    # tuỳ chọn: Vite dev server 5173 để sửa giao diện có hot reload
```

Test: `backend\.venv\Scripts\python -m pytest backend -q`

## Đóng gói exe

```powershell
cd frontend; npm run build        # build giao diện (exe dùng bản này, backend phục vụ)
cd ..\electron; npm install      # lần đầu; nếu npm chặn postinstall: node node_modules\electron\install.js
npm run build:exe                 # ra dist-app\Studio AI-win32-x64\Studio AI.exe
```

Exe là LỚP VỎ: nó dùng thư mục dự án này (backend/.venv, frontend/dist, jobs/), Ollama, OmniRoute và Docker đã cài trên máy, không đóng gói
sẵn chúng. Đường dẫn dự án ghi trong `resources\studio-root.txt` cạnh exe (đổi được bằng biến `STUDIO_ROOT`). Chuyển dự án sang thư mục khác
thì sửa file đó hoặc build lại. Muốn có biểu tượng trên Desktop: chuột phải `Studio AI.exe` > Send to > Desktop (create shortcut).

## Giao diện

- **Công việc:** danh sách job (tìm, lọc Cần bạn/Đang chạy/Xong); mỗi job có tab Tiến trình (ai đang cầm việc, 8 bước, sơ đồ bàn giao giữa nhân viên,
  dòng thời gian), Tài liệu, Nhật ký (lọc theo nhân viên, tìm, tải .txt), File (xem trước ảnh/văn bản).
- **Đội ngũ:** từng nhân viên: nhiệm vụ, công cụ, model, đang rảnh/làm/chờ bạn, việc đang giữ.
- **Hệ thống:** dịch vụ, sandbox, công cụ dòng lệnh, thử từng combo.
- Chế độ Sáng/Tối/Theo hệ thống (nút ở góc dưới thanh bên); thông báo khi job chuyển sang "chờ bạn" (toast, số trên tiêu đề, thông báo hệ thống nếu cho phép).

## Cấu hình (.env, mẫu ở .env.example)

- `LLM_MODE=direct`: gọi thẳng Ollama, ánh xạ combo -> model (`DIRECT_MODEL_*`). Dùng khi OmniRoute không chạy.
- `LLM_MODE=omniroute`: gửi tên combo (`brain/coder/fast/vision`) tới OmniRoute. Mặc định OmniRoute cắt yêu cầu sau 15 giây (lỗi 504) và
  giá trị toàn cục không chỉnh được. Cách chỉnh thật: dashboard > Providers > Ollama > sửa kết nối `ollama-local` >
  ô **Max Queue Wait (ms)** = 120000 (tối đa). Đã đặt; kết nối cloud mới thêm cũng nên đặt nếu model của chúng chậm.
- Khoá API cloud nhập trong dashboard OmniRoute, không ghi vào repo.

## Cấu trúc

```
backend/app/config.py        cấu hình từ .env
backend/app/llm/client.py    client OpenAI-compatible duy nhất
backend/app/agents/loop.py   vòng lặp agent bằng function calling (chịu model yếu)
backend/app/tools/sandbox.py 4 tool khoá trong jobs/<mã-job>/
backend/app/jobs/machine.py  máy trạng thái 8 bước, hai điểm dừng chờ người
backend/app/main.py          API FastAPI + SSE (+ /jobs/{id}/flow, /staff cho giao diện)
backend/app/staff.py         danh bạ nhân viên: nhiệm vụ, công cụ, combo
prompts/*.md                 prompt từng vai, nạp lúc chạy (sửa file là có hiệu lực ngay)
jobs/<mã-job>/               brief.md plan.md log.md work/ deliverables/ ...
frontend/                    React + Vite + TypeScript (build ra frontend/dist, backend phục vụ)
electron/                    vỏ exe: tự bật dịch vụ, cửa sổ riêng
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
