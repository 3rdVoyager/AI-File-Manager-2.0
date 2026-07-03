#!/usr/bin/env python3
"""AI File Manager 2.0 — launch local server and open browser."""

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import uvicorn


def find_port(start: int = 8000, end: int = 8019) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def open_browser(port: int) -> None:
    time.sleep(1.2)
    webbrowser.open(f"http://127.0.0.1:{port}")


def main() -> None:
    port = find_port()
    print(f"AI File Manager starting at http://127.0.0.1:{port}")
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
