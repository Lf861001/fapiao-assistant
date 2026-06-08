from __future__ import annotations

import socket
import threading
import time
import webbrowser

from app import app, prepare_folders


def find_free_port(start_port: int = 5000) -> int:
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("没有找到可用端口。")


def open_browser(url: str) -> None:
    time.sleep(1)
    webbrowser.open(url)


def main() -> None:
    prepare_folders()
    port = find_free_port()
    url = f"http://127.0.0.1:{port}/"
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
