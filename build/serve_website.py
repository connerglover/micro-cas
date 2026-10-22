"""Serve the built installer on localhost with WebTILP's isolation headers."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4173)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parents[1] / 'dist/website')
    args = parser.parse_args()
    if not (args.directory / 'index.html').is_file():
        parser.error('Build the website first: python build/website.py')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(args.directory)))
    print('MicroCAS installer: http://localhost:%d' % args.port, flush=True)
    server.serve_forever()
