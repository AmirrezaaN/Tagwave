"""Application entry point."""

from __future__ import annotations

import argparse
import ctypes
import os
import sys


def _message_box(text: str, title: str = "Tagwave") -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except Exception:
        print(text, file=sys.stderr)


def _parse(argv):
    p = argparse.ArgumentParser(prog="Tagwave", add_help=True)
    p.add_argument("paths", nargs="*")
    p.add_argument("--serve", action="store_true", help="run the backend only (development/testing)")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--token", default=None)
    p.add_argument("--debug", action="store_true")
    return p.parse_known_args(argv)[0]


def main(argv=None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    if sys.stdout is None:          # windowed build: keep prints from crashing
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    if args.serve:
        return _serve(args)

    from .instance import SingleInstance
    inst = SingleInstance()
    if not inst.acquire():
        if inst.send(args.paths):
            return 0

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Tagwave.MusicTagEditor")
    except Exception:
        pass

    from .api import Api
    from .server import Server
    api = Api()
    server = Server(api)
    server.start()

    try:
        import webview

        from .window import Native
    except Exception as exc:  # noqa: BLE001
        _message_box("Tagwave could not start its window component.\n\n%s" % exc)
        return 1

    native = Native(api, server.url, debug=args.debug)
    api.native = native

    def on_remote_paths(paths):
        if paths:
            api.add_paths(paths, origin="explorer")
        native.focus()

    try:
        inst.serve(on_remote_paths)
    except Exception:
        pass
    if args.paths:
        api.add_paths(args.paths, origin="explorer")

    cdp = os.environ.get("TAGWAVE_CDP_PORT")
    if cdp:
        webview.settings["REMOTE_DEBUGGING_PORT"] = int(cdp)
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
    try:
        webview.start(gui="edgechromium", debug=args.debug, private_mode=True)
    except Exception as exc:  # noqa: BLE001
        _message_box("Tagwave needs the Microsoft Edge WebView2 Runtime, which is part of Windows 10/11.\n"
                     "Please install it from Microsoft and try again.\n\nDetails: %s" % exc)
        return 1
    finally:
        server.stop()
        api.shutdown()
    return 0


def _serve(args) -> int:
    """Headless backend for UI development and automated tests."""
    from .api import Api
    from .server import Server
    api = Api()
    api.dev = True
    server = Server(api, port=args.port, token=args.token or "dev",
                    allow_hosts=("127.0.0.1:5173", "localhost:5173"))
    server.start()
    print("Tagwave backend on", server.url, flush=True)
    if args.paths:
        api.add_paths(args.paths)
    try:
        import threading
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        api.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
