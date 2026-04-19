# proxy_helper.py (запустить отдельно)
from flask import Flask, request, Response
import requests as req

app = Flask(__name__)

@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'}
    try:
        resp = req.get(url, headers=headers, timeout=15)
        return Response(resp.content, status=resp.status_code, content_type=resp.headers.get('content-type'))
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(port=8080)