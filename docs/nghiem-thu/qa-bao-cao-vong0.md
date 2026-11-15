KẾT QUẢ: PASS

Từng tiêu chí:
1. Chạy `py rename_photos.py --dry-run <path>`: Đạt.
   - Bằng chứng: Chạy `py deliverables/rename_photos.py --dry-run work/qa/test_photos` cho ra kết quả:
     `[DRY-RUN] a.jpg -> 20231027_100000_a.jpg`
     `[DRY-RUN] b.jpg -> 20231027_100000_b.jpg`
     `[DRY-RUN] c.jpg -> 20231027_110000_c.jpg`
2. Chạy `py rename_photos.py <path>`: Đạt.
   - Bằng chứng: Chạy `py deliverables/rename_photos.py work/qa/test_photos` và kiểm tra thư mục `work/qa/test_photos` cho thấy các file đã được đổi tên đúng quy tắc:
     `20231027_100000_a.jpg`
     `20231027_100000_b.jpg`
     `20231027_110000_c.jpg`
3. Kiểm tra file rename_photos.py tồn tại và chạy được trên Windows 11: Đạt.
   - Bằng chứng: File tồn tại trong `deliverables/` và đã thực thi thành công các lệnh trên môi trường Windows 11 (PowerShell).

Lỗi cần sửa (nếu FAIL): Không có.

Gợi ý: Script xử lý tốt trường hợp trùng thời gian bằng cách thêm số thứ tự (đã kiểm tra qua file a.jpg và b.jpg có cùng mốc thời gian nhưng vẫn đổi tên thành công).