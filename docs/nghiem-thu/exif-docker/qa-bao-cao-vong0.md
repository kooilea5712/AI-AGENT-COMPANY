KẾT QUẢ: PASS

Từng tiêu chí:
1. Chạy script với --dry-run: Đạt. Lệnh `python3 deliverables/rename_script.py work/qa/test_images --dry-run` in ra đúng danh sách file và tên mới dự kiến.
2. Chạy script thực tế: Đạt. Lệnh `python3 deliverables/rename_script.py work/qa/test_images` đã đổi tên các file trong thư mục `work/qa/test_images/` thành định dạng `YYYYMMDD_HHMMSS_tên_gốc.jpg`.
3. Kiểm tra fallback: Đạt. File `mtime_test.jpg` (không có EXIF) đã được đổi tên dựa trên ngày sửa file (20220520_100000).
4. Kiểm tra lỗi: Đạt. Script không bị crash khi gặp file `not_an_image.txt` (không phải ảnh) và file `corrupted.jpg` (file lỗi).

Lỗi cần sửa (nếu FAIL): Không có.

Gợi ý: Script hiện tại xử lý tốt các yêu cầu trong brief. Có thể cân nhắc thêm xử lý cho các định dạng ảnh khác (như .png) trong tương lai nếu khách hàng yêu cầu.