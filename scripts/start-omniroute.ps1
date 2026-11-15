# Khởi động OmniRoute chỉ trên loopback (mặc định của nó là 0.0.0.0, không khoá: ai trong LAN cũng tiêu được quota).
# Lưu ý: RATE_LIMIT_MAX_WAIT_MS KHÔNG đủ để nới giới hạn 15 giây (đã thử, vẫn 504); xem README, mục OmniRoute.
$env:OMNIROUTE_SERVER_HOST = '127.0.0.1'
omniroute serve --daemon --no-open
