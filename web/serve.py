"""로컬 HTTP 서버. wllama 의 멀티스레드(SharedArrayBuffer)에 필요한 COOP/COEP 헤더를 붙인다.

    python3 web/serve.py [포트=8765]                            # 저장소 루트 → http://127.0.0.1:8765/web/e2e.html
    python3 web/serve.py 8780 --root out/site --host 0.0.0.0    # 데모 사이트(web/demo/build.sh)를 사내망에 띄운다
    python3 web/serve.py 8781 --root out/site --host 0.0.0.0 --tls cert.pem key.pem   # HTTPS (자체 서명 인증서)

브라우저는 HTTPS 나 localhost 에서만 COOP/COEP 를 따른다. 사내망 HTTP 주소로 열면 단일 스레드로 돈다.
"""

import argparse
import http.server
import ssl
from functools import partial
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


ap = argparse.ArgumentParser()
ap.add_argument("port", type=int, nargs="?", default=8765)
ap.add_argument("--root", default=".", help="띄울 폴더 (저장소 루트 기준)")
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--tls", nargs=2, metavar=("CERT", "KEY"))
a = ap.parse_args()

srv = http.server.ThreadingHTTPServer((a.host, a.port), partial(Handler, directory=str(LAB / a.root)))
if a.tls:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(*a.tls)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
srv.serve_forever()
