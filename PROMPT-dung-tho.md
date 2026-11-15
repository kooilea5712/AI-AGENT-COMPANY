# Bối cảnh
Tôi là sinh viên năm hai ngành kỹ thuật phần mềm, biết cơ bản Python, C++ và SQL, làm một mình. Tôi muốn dựng bản thô của một "studio freelance AI": ứng dụng chạy trên máy cá nhân, trong đó một nhóm AI agent nhận job (phần mềm, ảnh, vector, video, âm thanh, game), tự làm và bàn giao file, còn tôi chỉ duyệt ở hai điểm. Thiết kế đầy đủ nằm ở docs/thiet-ke.md trong thư mục này. Hãy đọc nó trước: nó là nguồn sự thật về vai trò, quy trình 8 bước, quy ước thư mục job và nội dung prompt của từng agent.

Bạn đang chạy với quyền shell trên chính máy đó. Việc của bạn trong phiên này là cài những thứ còn thiếu và dựng bản thô chạy được từ đầu đến cuối cho một job phần mềm nhỏ. "Thô" nghĩa là đủ luồng, ít tính năng, code dễ đọc để tôi học và sửa tiếp. Không cần đẹp, không cần tối ưu.

# Máy
- CPU Intel Core i5-14400F, RAM 32 GB DDR4, GPU RTX 5070 12 GB VRAM. Tôi dùng Windows 11; hãy tự kiểm tra hệ điều hành, shell và trình quản lý gói có sẵn trước khi cài.
- 12 GB VRAM chỉ đủ nạp một model local cỡ 12 đến 14B tại một thời điểm, nên backend gọi model local tuần tự, không song song.

# Cài đặt
Kiểm tra từng mục, chỉ cài cái còn thiếu, ghi phiên bản vào docs/moi-truong.md:
- Git, Python 3.12 trở lên, Node.js LTS.
- Ollama, rồi kéo ba model: một model code cỡ 14B (ứng viên: qwen2.5-coder:14b), một model đa phương thức có vision và tool calling cỡ 12B (ứng viên: gemma4:12b), một model nhỏ nhanh cỡ 4B. Tag đổi thường xuyên: xem ollama.com/library để chọn tag hiện hành vừa 12 GB. Thử gọi tool thật với từng model trước khi chốt, vì có model khai báo hỗ trợ tool nhưng trả tool call sai định dạng.
- OmniRoute (gói npm omniroute, cổng mặc định localhost:20128/v1). Đọc tài liệu của phiên bản cài được rồi tạo bốn combo brain, coder, fast, vision, và thêm Ollama làm nhà cung cấp cuối của mỗi combo. Tôi sẽ tự nhập khoá API cloud trong dashboard của OmniRoute; đừng hỏi khoá trong chat và đừng ghi khoá vào file nào trong repo.
- FFmpeg, ImageMagick, Inkscape. Chúng dùng cho giai đoạn media sau; cài luôn để trang kiểm tra hệ thống báo đủ.
Tôi đồng ý trước cho việc cài các mục trên và tải ba model đó. Dừng lại hỏi tôi nếu cần cài thứ ngoài danh sách, cần khởi động lại máy, hoặc một lệnh đòi quyền admin mà bạn không chắc tác dụng. Docker, ComfyUI, Blender, Godot chưa cài ở phiên này.

# Kiến trúc bản thô
Backend: Python, FastAPI, SQLite.
- Lớp LLM: một client OpenAI-compatible duy nhất, base URL và tên combo đọc từ .env. Agent chỉ gọi theo tên combo. Có biến cấu hình để trỏ thẳng vào Ollama (localhost:11434/v1) khi OmniRoute chưa có khoá, để tôi thử được ngay.
- Vòng lặp agent tự viết bằng function calling, không dùng framework agent ở bản này. Luồng 8 bước có hai điểm dừng chờ người và cần lưu trạng thái; viết thẳng thành máy trạng thái thì tôi đọc hiểu và gỡ lỗi được. Tách giao diện đủ gọn để sau này thay bằng CrewAI hoặc LangGraph.
- Vòng lặp phải chịu được model yếu: tool call sai định dạng thì trả lỗi lại cho model và cho thử lại; giới hạn số bước mỗi task; giới hạn hai vòng sửa sau khi Kiểm định trả FAIL; mọi lần gọi model và tool đều ghi vào log.
- Tool cho agent: đọc file, ghi file, liệt kê thư mục, chạy lệnh. Tất cả bị khoá trong jobs/<mã-job>/ (chặn đường dẫn thoát ra ngoài), lệnh có timeout và có danh sách lệnh bị cấm. Đây là thay thế tạm cho sandbox Docker; ghi rõ giới hạn của nó trong README.
- Agent ở bản này: Giám đốc điều phối, Kỹ sư phần mềm, Kiểm định. Prompt của từng vai nằm trong prompts/*.md, lấy nguyên văn từ docs/thiet-ke.md và nạp lúc chạy, để tôi sửa prompt mà không phải sửa code. Chuyên viên media chỉ để chỗ trống có ghi chú.
- Máy trạng thái job theo đúng 8 bước trong thiết kế, dừng ở "chờ duyệt brief" và "chờ duyệt bàn giao". Trạng thái lưu trong SQLite; brief.md, plan.md, log.md, HANDOFF.md và sản phẩm lưu trong thư mục job. Backend tắt giữa chừng thì khi khởi động lại job phải tiếp tục được từ bước gần nhất, hoặc ít nhất được đánh dấu rõ là bị ngắt.
- API: tạo job, liệt kê job, xem chi tiết, trả lời câu hỏi của Giám đốc, duyệt hoặc trả lại brief, duyệt hoặc trả lại bàn giao, dòng sự kiện trực tiếp (SSE), liệt kê và tải file của job, và /health kiểm tra OmniRoute, Ollama, từng combo, từng công cụ dòng lệnh.

Frontend: React, Vite, TypeScript, một trang, giao diện tiếng Việt.
- Danh sách job kèm trạng thái; form tạo job gồm mô tả và file đính kèm.
- Trang chi tiết job: tiến trình 8 bước, brief hiển thị dạng markdown với nút Duyệt và Trả lại kèm ghi chú, nhật ký chạy trực tiếp, báo cáo Kiểm định, danh sách file tải được, nút Duyệt bàn giao.
- Trang Hệ thống: kết quả /health và model nào đang phục vụ mỗi combo.
- Giao diện đơn giản, sạch, không cần thư viện UI nặng.

# Cách làm
- Trước khi viết code: đọc docs/thiet-ke.md, kiểm tra máy, rồi gửi tôi kế hoạch ngắn (cấu trúc thư mục, các mốc) và những chỗ thiết kế còn mơ hồ. Chỗ nào đoán sai dễ sửa thì tự quyết và ghi lại; chỗ nào đoán sai phải làm lại nhiều thì hỏi.
- Làm theo mốc, mỗi mốc chạy được và commit Git riêng: (1) môi trường và /health, (2) lớp LLM và một agent dùng tool trong thư mục job, (3) máy trạng thái đủ 8 bước với ba agent, (4) frontend, (5) chạy thử đầu cuối.
- Viết test cho phần dễ sai mà khó thấy: khoá đường dẫn của tool, chuyển trạng thái job, xử lý tool call hỏng.
- Không giả lập kết quả. Nếu một phần chưa chạy thật, ví dụ OmniRoute chưa có khoá, hãy nói rõ thay vì trả dữ liệu mẫu.
- Tôi đang học, nên hãy comment ở những chỗ có quyết định thiết kế (vì sao làm vậy) và bỏ qua những dòng hiển nhiên.

# Nghiệm thu
Chạy thật một job qua giao diện: "Viết script Python đổi tên hàng loạt file ảnh trong một thư mục theo ngày chụp, có chế độ chạy thử". Xong khi: brief hiện ra chờ tôi duyệt; sau khi duyệt, Kỹ sư viết và tự chạy script; Kiểm định trả PASS hoặc FAIL có bằng chứng; HANDOFF.md và script nằm trong deliverables/; toàn bộ nhật ký xem được trên giao diện.

Kết thúc phiên, báo cho tôi: cái gì đã chạy thật và bằng chứng; cái gì chưa chạy và vì sao; model local nào bạn chốt cho từng combo kèm kết quả thử tool call; lệnh khởi động backend và frontend; ba việc nên làm tiếp theo.