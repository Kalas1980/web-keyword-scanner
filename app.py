import json
import os
import queue
import threading
import time
import uuid
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, Response, jsonify, render_template, request

app = Flask(__name__)

# Active scans: scan_id -> {"queue": Queue, "done": bool, "ts": float}
scans: dict = {}
_scan_lock = threading.Lock()
MAX_CONCURRENT_SCANS = 10   # public safety cap
SCAN_TTL_SECONDS = 3600     # evict finished scans after 1 hour

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KeywordScanner/1.0)"}


def _get_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def _snippets(text: str, keyword: str, context: int = 90) -> str:
    idx = text.find(keyword)
    if idx < 0:
        return ""
    start = max(0, idx - context)
    end = min(len(text), idx + len(keyword) + context)
    return "…" + text[start:end].replace("\n", " ") + "…"


def _normalise_url(url: str) -> str:
    url = url.strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _evict_old_scans() -> None:
    """Remove scans that finished more than SCAN_TTL_SECONDS ago."""
    cutoff = time.time() - SCAN_TTL_SECONDS
    with _scan_lock:
        stale = [sid for sid, s in scans.items() if s["done"] and s["ts"] < cutoff]
        for sid in stale:
            del scans[sid]


def crawl_and_scan(
    scan_id: str,
    start_urls: list[str],
    keywords: list[str],
    max_depth: int,
    max_pages: int,
    same_domain_only: bool,
    q: queue.Queue,
) -> None:
    visited: set[str] = set()
    queued: set[str] = set(start_urls)   # URLs already in the frontier
    # (url, depth)
    frontier: list[tuple[str, int]] = [(u, 0) for u in start_urls]
    base_domains = {urlparse(u).netloc for u in start_urls}
    kw_lower = [k.lower() for k in keywords]
    pages_scanned = 0
    matches_found = 0

    while frontier and pages_scanned < max_pages:
        url, depth = frontier.pop(0)
        if url in visited:
            continue
        visited.add(url)

        q.put({"type": "progress", "url": url, "scanned": pages_scanned, "found": matches_found})

        try:
            resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
            ct = resp.headers.get("content-type", "")
            if "text/html" not in ct:
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            text = _get_text(soup).lower()
            url_lower = url.lower()

            hit_keywords = []
            for kw in kw_lower:
                if kw in text or kw in url_lower:
                    snippet = _snippets(text, kw)
                    hit_keywords.append({"keyword": kw, "snippet": snippet})

            if hit_keywords:
                matches_found += 1
                q.put({"type": "match", "url": url, "matches": hit_keywords})

            pages_scanned += 1

            if depth < max_depth:
                for a in soup.find_all("a", href=True):
                    full = urljoin(url, str(a["href"]))
                    p = urlparse(full)
                    if p.scheme not in ("http", "https"):
                        continue
                    if same_domain_only and p.netloc not in base_domains:
                        continue
                    if full not in visited and full not in queued:
                        queued.add(full)
                        frontier.append((full, depth + 1))

        except Exception as exc:
            q.put({"type": "error", "url": url, "error": str(exc)})

    q.put({"type": "done", "scanned": pages_scanned, "found": matches_found})
    scans[scan_id]["done"] = True
    scans[scan_id]["ts"] = time.time()
    _evict_old_scans()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scan", methods=["POST"])
def start_scan():
    data = request.get_json(force=True)

    raw_start = _normalise_url(data.get("start_url", ""))
    raw_list = data.get("url_list", "").strip()
    keywords = [k.strip() for k in data.get("keywords", "").split(",") if k.strip()]
    try:
        max_depth = max(0, min(int(data.get("max_depth", 2)), 5))
        max_pages = max(1, min(int(data.get("max_pages", 50)), 200))
    except (ValueError, TypeError):
        return jsonify({"error": "max_depth and max_pages must be integers."}), 400
    same_domain_only = bool(data.get("same_domain_only", True))

    if not keywords:
        return jsonify({"error": "Enter at least one keyword."}), 400

    with _scan_lock:
        active = sum(1 for s in scans.values() if not s["done"])
    if active >= MAX_CONCURRENT_SCANS:
        return jsonify({"error": "Server is busy — too many active scans. Try again shortly."}), 429

    start_urls = []
    if raw_start:
        start_urls.append(raw_start)
    for line in raw_list.splitlines():
        u = _normalise_url(line)
        if u:
            start_urls.append(u)

    if not start_urls:
        return jsonify({"error": "Enter at least one URL."}), 400

    scan_id = str(uuid.uuid4())
    q: queue.Queue = queue.Queue()
    scans[scan_id] = {"queue": q, "done": False, "ts": time.time()}

    threading.Thread(
        target=crawl_and_scan,
        args=(scan_id, start_urls, keywords, max_depth, max_pages, same_domain_only, q),
        daemon=True,
    ).start()

    return jsonify({"scan_id": scan_id})


@app.route("/stream/<scan_id>")
def stream(scan_id: str):
    if scan_id not in scans:
        return jsonify({"error": "Scan not found."}), 404

    def generate():
        scan = scans[scan_id]
        q = scan["queue"]
        while True:
            try:
                item = q.get(timeout=1.0)
                yield f"data: {json.dumps(item)}\n\n"
                if item.get("type") == "done":
                    break
            except queue.Empty:
                if scan["done"]:
                    break
                yield "data: {\"type\":\"ping\"}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=os.environ.get("FLASK_ENV") != "production", port=port, threaded=True)
