# Studio AI

Một "studio freelance" gồm các AI agent. Bạn chỉ làm việc với **Giám đốc điều phối**: giao việc, trả lời khi Giám đốc hỏi, nhắn thêm (kèm file),
rồi xem kết quả cuối và chỉ ra lỗi. Phần còn lại cả đội tự làm trong sandbox.
Thiết kế gốc: `docs/thiet-ke.md`. Phiên bản công cụ và model: `docs/moi-truong.md`. Bằng chứng chạy thử: `docs/nghiem-thu/`.

## Luồng một job

```
Bạn ──giao việc──▶ Giám đốc (Claude Opus)
                     1 tiếp nhận, hỏi lại nếu bắt buộc, viết brief
                     2 TỰ CHỐT DUYỆT brief          (bật "tôi muốn tự duyệt brief" trong Cài đặt nếu muốn giữ cổng này)
                     3 chia việc: plan.json = nhiều task, mỗi task một model con
                       ├─ Kỹ sư phần mềm   (code, script)
                       └─ Chuyên viên media (logo, vector, ảnh, PDF bằng ArtCraft/Inkscape/ImageMagick)
                     4 các task chạy theo phụ thuộc; sau MỖI task hệ thống commit Git
                   Kiểm định (Claude Sonnet)   viết bộ testcase từ brief + sản phẩm
                   Kiểm thử viên (Haiku/free)  chạy HẾT testcase, mỗi case một lượt; code chạy lại độc lập các case đo được
                     FAIL -> model con sửa (tối đa 2 vòng)    testcase hỏng -> trả Kiểm định sửa
                     7 Giám đốc viết HANDOFF.md
Bạn ◀──xem kết quả cuối── chấp nhận, hoặc chỉ lỗi / giao thêm (kèm file) -> Giám đốc lập kế hoạch bổ sung (đợt mới)
```

Chủ chỉ nói chuyện với Giám đốc: tab **Giám đốc** trong mỗi job là hội thoại; nhắn lúc job đang chạy thì tin được xếp hàng cho Giám đốc đọc ở bước kế tiếp.
Mọi hành động (trả lời, phản hồi, tiếp tục job dừng) đều đính kèm được file; file lưu ở `jobs/<mã-job>/inputs/` và agent đọc qua `@job/inputs/...`.

## Chạy

**Cách chính: mở `Studio AI.exe`** (xem "Đóng gói exe"). Nó tự bật Docker Desktop (nếu có), Ollama, OmniRoute (chỉ loopback) và backend, đợi sẵn sàng
rồi mở giao diện trong cửa sổ riêng. Đóng cửa sổ thì nó tắt đúng những dịch vụ nó đã bật. Nhật ký launcher: `%APPDATA%\Studio AI\logs\`.

Chạy tay (để phát triển), mỗi lệnh một cửa sổ PowerShell, từ thư mục gốc repo:

```powershell
.\scripts\start-omniroute.ps1   # tuỳ chọn, chỉ cần nếu dùng OmniRoute (bind loopback)
.\scripts\start-backend.ps1     # http://127.0.0.1:8000, đồng thời phục vụ giao diện build sẵn (frontend/dist)
.\scripts\start-frontend.ps1    # tuỳ chọn: Vite dev server 5173 để sửa giao diện có hot reload
```

Test: `backend\.venv\Scripts\python -m pytest backend -q`

## Cài đặt model (trang Cài đặt, không cần sửa file)

Mỗi vai có **danh sách ứng viên** theo thứ tự ưu tiên; lỗi (mạng, hết quota, thiếu khoá) thì tự dùng ứng viên kế.

| Vai | Mặc định |
| --- | --- |
| Giám đốc điều phối | Claude Opus 5.5 -> OmniRoute `brain` -> Ollama |
| Kiểm định (thiết kế testcase) | Claude Sonnet 5.5 -> OmniRoute -> Ollama |
| Kiểm thử viên (chạy testcase) | Claude Haiku 5.5 -> OmniRoute `fast` (model free) -> Ollama |
| Kỹ sư phần mềm, Chuyên viên media, Mắt (vision) | OmniRoute -> Ollama |

- **Khoá API** nhập ở Cài đặt, lưu trong `~/.studio-ai/settings.json` (NGOÀI repo, không vào Git, không hiện lại trên màn hình). Chưa nhập khoá thì ứng viên Claude bị bỏ qua và cả đội chạy bằng model dự phòng; banner trên trang Công việc báo điều này.
- **Laptop không có Ollama:** chọn preset "Toàn bộ dùng Claude", hoặc tắt kết nối Ollama; ứng viên lỗi vốn tự bị bỏ qua.
- Tên model Claude (`claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`) đổi được khi có bản mới. Claude đi qua endpoint tương thích OpenAI của Anthropic (`https://api.anthropic.com/v1`).
- Thêm nhà cung cấp OpenAI-compatible khác (OpenRouter, LM Studio...) ngay trong Cài đặt. Nút "Thử" gọi thật từng vai và cho biết ứng viên nào đã phục vụ.
- OmniRoute: mặc định cắt yêu cầu sau 15 giây (lỗi 504) và giá trị toàn cục không chỉnh được. Chỉnh thật: dashboard > Providers > Ollama > sửa kết nối `ollama-local` > **Max Queue Wait (ms)** = 120000.

## Làm trực tiếp trên máy + Git

Khi tạo job, ô **"Làm trực tiếp trên một thư mục trong máy"** gắn job với một project:
- Agent sửa thẳng file trong thư mục đó, trên nhánh riêng `studio/<mã-job>` tách từ nhánh hiện tại. Không bao giờ đụng nhánh khác, không push, không force; muốn đưa vào nhánh chính bạn tự `git merge`.
- Thư mục phải sạch (không có thay đổi chưa commit). Chưa là repo thì tự `git init` và tạo commit gốc. Từ chối thư mục hệ thống/quá rộng (ổ đĩa gốc, thư mục home, Windows, Program Files, AppData) và thư mục con của một repo lớn hơn.
- **Commit bắt buộc:** sau MỖI lần agent chạy xong (brief, kế hoạch, từng task, testcase, kiểm thử, bàn giao) hệ thống tự commit, kể cả khi không có thay đổi (`--allow-empty` để mỗi lần chạy đều có dấu vết). Không commit được (ví dụ hook từ chối) thì job dừng, không bỏ qua hook. Tab **Git** của job liệt kê commit và xem file đã đổi.
- Kiểm định/Kiểm thử chạy trên **bản sao dùng một lần** của project (mount chỉ-đọc), nên testcase đổi tên/xoá file cũng không đụng project thật.
- Job thường (không gắn project) cũng là một repo Git ngay trong `jobs/<mã-job>/`.

## ArtCraft cho Chuyên viên media

ArtCraft (mã nguồn mở, bạn đã cài) cung cấp `vectorcraft-cli` (vẽ vector bằng lệnh JSON, xuất SVG/PNG/PDF; 885 lệnh, tra bằng tool `craft_help`) và `pdfcraft-cli`
(PDF). Là bản Windows nên chạy trên máy chứ không trong Docker, qua tool `craft` có kiểm soát: chỉ whitelist lệnh con (không `mcp`/`ui`), mọi đường dẫn trong đối số
và trong file lệnh JSON phải nằm trong thư mục làm việc, không qua shell. Đường dẫn CLI đặt bằng `VECTORCRAFT_CLI`/`PDFCRAFT_CLI` trong `.env` nếu cài chỗ khác.
Ứng dụng ArtCraft có giao diện (tạo ảnh/video bằng API đám mây tính credit) không script được nên không dùng.

## Kiểm định

- Kiểm định (model mạnh) đọc brief + bản chụp sản phẩm và viết `qa/testcases.json`: mỗi case có `setup`, `steps`, `expect` (exit_code, stdout_contains...) hoặc `manual_check`.
- Kiểm thử viên (model rẻ) chạy **từng case một lượt gọi riêng** (model nhỏ hay bỏ dở giữa danh sách dài).
- **Chống ghi bừa PASS:** case có `expect` thì code tự chạy lại trong sandbox và so với `expect`; kết quả của code thắng. Case còn lại tin Kiểm thử viên.
- Setup của testcase hỏng thì đó là lỗi **testcase**, không đổ cho model con: trả về Kiểm định sửa (tối đa 2 lần), sau đó loại case đó và ghi rõ trong báo cáo.

## Đóng gói exe

```powershell
cd frontend; npm run build        # build giao diện (exe dùng bản này, backend phục vụ)
cd ..\electron; npm install      # lần đầu; nếu npm chặn postinstall: node node_modules\electron\install.js
npm run build:exe                 # ra dist-app\Studio AI-win32-x64\Studio AI.exe
```

Exe là LỚP VỎ: nó dùng thư mục dự án này (backend/.venv, frontend/dist, jobs/), Ollama, OmniRoute và Docker đã cài trên máy, không đóng gói sẵn chúng.
Đường dẫn dự án ghi trong `resources\studio-root.txt` cạnh exe (đổi bằng biến `STUDIO_ROOT`). Chuyển dự án sang thư mục khác thì sửa file đó hoặc build lại.

## Giao diện

- **Công việc:** danh sách job (tìm, lọc); mỗi job có tab Tiến trình (ai đang cầm việc, 8 bước, sơ đồ bàn giao, bảng task, dòng thời gian), Giám đốc (hội thoại + đính kèm), Tài liệu (brief, kế hoạch, testcase, báo cáo, HANDOFF), Nhật ký (lọc theo nhân viên), File (xem trước), Git.
- **Đội ngũ:** từng nhân viên: nhiệm vụ, công cụ, chuỗi model, đang rảnh/làm/chờ bạn.
- **Cài đặt:** nhà cung cấp, model theo vai, preset, công tắc duyệt brief, chế độ sandbox.
- **Hệ thống:** dịch vụ, sandbox, ArtCraft, công cụ dòng lệnh, thử gọi từng vai.
- Sáng/Tối/Theo hệ thống; thông báo khi job chuyển sang "chờ bạn".

## Cấu trúc

```
backend/app/settings.py      nhà cung cấp + model theo vai (~/.studio-ai/settings.json)
backend/app/llm/client.py    client OpenAI-compatible, định tuyến theo vai, ứng viên dự phòng
backend/app/agents/loop.py   vòng lặp agent bằng function calling (chịu model yếu)
backend/app/tools/sandbox.py công cụ theo vai: file, run_command (Docker), describe_image, craft (ArtCraft)
backend/app/jobs/machine.py  máy trạng thái: duyệt brief, chia task, thực thi, testcase, bàn giao, phản hồi
backend/app/planning.py      kiểm tra plan.json và testcases.json bằng code
backend/app/gitops.py        Git: nhánh riêng, commit bắt buộc, chặn thư mục nguy hiểm
backend/app/main.py          API FastAPI + SSE
prompts/*.md                 prompt từng vai, nạp lúc chạy (sửa file là có hiệu lực ngay)
frontend/  electron/  docker/sandbox/  ollama/*.Modelfile
```

`prompts/phu-*.md`, `giam-doc-*.md`, `kiem-*.md` là phần do code thêm (giao thức, nhiệm vụ từng bước); các file còn lại lấy nguyên văn từ thiết kế.

## Sandbox

`sandbox_mode=docker` (mặc định): mỗi lệnh của agent chạy trong container dùng một lần từ image `studio-sandbox` (Debian + Python 3.12 + Pillow + ffmpeg + ImageMagick 7 + Inkscape + git):
không mạng, 2 GB RAM, 2 CPU, 256 tiến trình, bỏ hết capability, chỉ mount thư mục làm việc (và thư mục job chỉ-đọc). Dựng image một lần:
`docker build -t studio-sandbox docker/sandbox` (khoảng 1,3 GB). `local` chỉ là PowerShell + danh sách đen từ khoá, KHÔNG cô lập.
Giờ trong container là UTC. `read_file`/`write_file` chạy trên host và bị chặn thoát khỏi thư mục làm việc/thư mục job (có test); Giám đốc chỉ ghi được tài liệu job, Kiểm định chỉ ghi được `qa/`.

## Giới hạn đã biết

- Video, âm thanh, game, ảnh tạo sinh chưa có. Chất lượng thẩm mỹ của media còn yếu: kiểm thử chỉ kiểm được thứ đo được; mắt thẩm mỹ là bạn ở bước xem kết quả cuối.
- Model local chạy tuần tự và chậm; model cỡ nhỏ làm Kiểm thử viên/Kiểm định kém ổn định (hay thiết kế testcase hỏng, bỏ dở). Dùng Claude cho các vai này khi có khoá.
- Phần Claude API chưa được thử với khoá thật (không có khoá trong phiên làm việc); đường gọi được test bằng giả lập và đi qua cùng client với các nhà cung cấp khác.
- Job `blocked`: bấm "Tiếp tục từ bước đã dừng" (kèm hướng dẫn/file). Giám đốc chỉ hỏi một lượt; `lessons.md` ở gốc repo được nạp vào prompt.
