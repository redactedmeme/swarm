"""Serves the REDACTED token volume dashboard."""
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(__file__), **kwargs)

    def do_GET(self):
        if self.path == '/' or self.path == '':
            self.path = '/index.html'
        return super().do_GET()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, max-age=300')
        super().end_headers()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3001))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f'Dashboard running on port {port}')
    server.serve_forever()
