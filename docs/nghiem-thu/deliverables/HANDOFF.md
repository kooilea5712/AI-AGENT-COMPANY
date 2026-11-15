Đã hoàn thành script Python để đổi tên hàng loạt file ảnh dựa trên thời gian chỉnh sửa.

Cách chạy:
- Chế độ xem trước: `py deliverables/rename_photos.py --dry-run <đường-dẫn-thư-mục>`
- Chế độ thực thi: `py deliverables/rename_photos.py <đường-dẫn-thư-mục>`

Giới hạn:
- Chỉ xử lý dựa trên thời gian chỉnh sửa file (Modification Time), không đọc dữ liệu EXIF bên trong ảnh.
- Chỉ sử dụng thư viện chuẩn của Python.

Giả định:
- Nếu có nhiều file cùng thời gian chỉnh sửa, script tự động thêm số thứ tự (ví dụ: _1, _2) để tránh trùng lặp.
