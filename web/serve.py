"""저장소 루트를 로컬 HTTP 로 띄운다. wllama 의 멀티스레드(SharedArrayBuffer)에 필요한 COOP/COEP 헤더를 붙인다.

    python3 web/serve.py [포트=8765]     # → http://127.0.0.1:8765/web/e2e.html
"""

import http.server
import os
import sys
from pathlib import Path


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


os.chdir(Path(__file__).resolve().parents[1])
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), Handler).serve_forever()
