# Chạy backend (cổng 8000, chỉ loopback). Cấu hình đọc từ .env ở gốc repo.
Set-Location "$PSScriptRoot\..\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
