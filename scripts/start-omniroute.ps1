# Khởi động OmniRoute chỉ trên loopback (mặc định của nó là 0.0.0.0, không khoá: ai trong LAN cũng tiêu được quota).
$env:OMNIROUTE_SERVER_HOST = '127.0.0.1'
omniroute serve --daemon --no-open
