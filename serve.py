"""
Windows üretim başlatıcısı — Waitress WSGI sunucusu.

IIS + httpPlatformHandler ile çalışırken IIS, Python sürecini kendisi başlatır
ve dinlenecek portu HTTP_PLATFORM_PORT ortam değişkeniyle verir. Bu script o
portu otomatik okur. httpPlatformHandler kullanılmadan elle de çalıştırılabilir
(o zaman PORT / varsayılan 8000 kullanılır).

Elle çalıştırma:
    python serve.py
    set PORT=8001 & python serve.py
"""
import os

from waitress import serve

from config.wsgi import application

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    # httpPlatformHandler dinlenecek portu HTTP_PLATFORM_PORT ile verir.
    port = int(os.environ.get("HTTP_PLATFORM_PORT") or os.environ.get("PORT", "8000"))
    threads = int(os.environ.get("THREADS", "8"))
    print(
        f"E-Mutabakat (Waitress) dinliyor: http://{host}:{port}  (threads={threads})",
        flush=True,
    )
    serve(application, host=host, port=port, threads=threads)
