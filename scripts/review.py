"""Private loopback review of one prepared project."""
import argparse
import base64
import fcntl
import hashlib
import json
import math
import mimetypes
import re
import secrets
import socket
import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import story_preview
import feedback
import project_context
from prepare import project_data, read, version, write_json


def human(folder):
    file = folder / "human.json"
    return read(file) if file.exists() else {"revision": 0, "segments": {}}


def model(folder):
    raw = (folder / "model.json").read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


class Review(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Session URLs stay out of access logs.

    def route(self):
        if self.headers.get("Host") != self.server.address:
            raise PermissionError
        parts = urlsplit(self.path).path.strip("/").split("/")
        if parts.pop(0) != self.server.token:
            raise PermissionError
        if self.server.library:
            self.server.projects = library_projects(self.server.library)
        self.root = self.server.root
        if parts[:1] == ["p"]:
            if len(parts) < 2 or parts[1] not in self.server.projects:
                raise KeyError
            self.root = self.server.projects[parts[1]]
            return parts[2:]
        return parts

    def reply(self, body, mime):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def project(self):
        return read(self.root / "project.json")

    def asset(self, key):
        project = self.project()
        if not re.fullmatch("[0-9a-f]{24}", key) or key not in project["assets"].values():
            raise KeyError
        folder = self.root / "assets" / key
        return folder, read(folder / "asset.json")

    def media(self, path):
        size = path.stat().st_size
        start, end = 0, size-1
        span = self.headers.get("Range")
        if span:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", span)
            if not match or not any(match.groups()):
                return self.send_error(416)
            left, right = match.groups()
            if left:
                start = int(left)
                end = min(end, int(right)) if right else end
            else:
                start = max(0, size-int(right))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        with path.open("rb") as file:
            self.send_response(206 if span else 200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end-start+1))
            if span:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            file.seek(start)
            remaining = end-start+1
            while remaining:
                data = file.read(min(262144, remaining))
                if not data:
                    break
                self.wfile.write(data)
                remaining -= len(data)

    def do_GET(self):
        try:
            parts = self.route()
            if parts == ["ready.gif"]:
                return self.reply(base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="), "image/gif")
            if len(parts) <= 1 and (not parts or parts[0] in {"review.js","review.css","story.html","story.js","timeline.js","story.css"}):
                name = parts[0] if parts else "index.html"
                return self.reply((self.server.resources/name).read_bytes(), mimetypes.guess_type(name)[0]+"; charset=utf-8")
            if parts == ["stories"]:
                directory = self.root / "stories"
                value = []
                for path in sorted(directory.glob("*/story.json"), reverse=True):
                    if re.fullmatch(r"[a-zA-Z0-9_-]+", path.parent.name):
                        value.append(dict(id=path.parent.name, **read(path)))
                return self.reply(json.dumps(value).encode(), "application/json")
            if len(parts) == 3 and parts[0] == "stories" and parts[2] == "preview.mp4":
                if not re.fullmatch(r"[a-zA-Z0-9_-]+", parts[1]):
                    raise KeyError
                return self.media(self.root / "stories" / parts[1] / "preview.mp4")
            if parts == ["projects"]:
                value = [{"id": pid, "title": read(root/"project.json")["title"]}
                         for pid, root in self.server.projects.items()]
            elif parts == ["project"]:
                p = self.project()
                with feedback.database(self.root) as db:
                    queued = [key for key in p["assets"].values() if feedback.get(db,key)["pending"]]
                durations = {}
                for key in p["assets"].values():
                    if re.fullmatch("[0-9a-f]{24}", key):
                        durations[key] = read(self.root / "assets" / key / "asset.json")["duration"]
                value = dict(title=p["title"], assets=p["assets"], durations=durations,
                             pending=queued, context=project_context.get(self.root))
            elif len(parts) == 2:
                key, action = parts
                folder, meta = self.asset(key)
                if action == "source":
                    base = (self.root / self.project()["source_root"]).resolve()
                    path = (base / meta["source"]).resolve()
                    if base not in path.parents or version(path) != meta["version"]:
                        return self.send_error(409, "Source changed")
                    return self.media(path)
                if re.fullmatch(r"frame-[1-4]\.jpg", action):
                    return self.media(folder/action)
                if action != "detail":
                    raise KeyError
                draft, stamp = model(folder)
                with feedback.database(self.root) as db:
                    note = feedback.get(db,key)
                value = dict(asset=meta, model=draft, stamp=stamp, human=human(folder), feedback=note)
            else:
                raise KeyError
            self.reply(json.dumps(value).encode(), "application/json")
        except PermissionError:
            self.send_error(403)
        except (KeyError, FileNotFoundError):
            self.send_error(404)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        try:
            parts = self.route()
            if self.headers.get("Origin") != "http://"+self.server.address:
                raise PermissionError
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 131072:
                return self.send_error(413)
            data = json.loads(self.rfile.read(length))
            if parts in (["stories", "timeline"], ["stories", "trim"]):
                try:
                    edition = story_preview.save_trims(self.root,data["base"],data["ranges"],data.get("removed"))
                except (ValueError, KeyError, OSError) as error:
                    self.send_response(400)
                    self.send_header("Content-Type","application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(error)}).encode())
                    return
                return self.reply(json.dumps({"edition":edition}).encode(),"application/json")
            if parts == ["context"]:
                state = project_context.update(self.root,data["revision"],data["raw"])
                return self.reply(json.dumps(state).encode(), "application/json")
            if len(parts) != 2 or parts[1] not in {"correct","feedback"}:
                raise KeyError
            folder, meta = self.asset(parts[0])
            if parts[1] == "feedback":
                note = feedback.save(self.root,parts[0],data["revision"],data["pending"])
                return self.reply(json.dumps(note).encode(), "application/json")
            with (folder / ".human.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                saved = human(folder)
                draft, stamp = model(folder)
                if data["revision"] != saved["revision"] or data["stamp"] != stamp:
                    return self.send_error(409, "Reload before saving")
                segment = data["segment"]
                sid = segment["id"]
                if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", sid):
                    raise ValueError
                original = next((s for s in draft["segments"] if s["id"] == sid), {})
                prior = saved["segments"].get(sid, original)
                if not prior and not sid.startswith("human-"):
                    raise ValueError
                if prior and prior["kind"] != segment["kind"]:
                    raise ValueError
                if segment["kind"] not in {"visual", "speech", "sound", "inference", "suggestion", "note"}:
                    raise ValueError
                for field in ("text", "speaker", "role"):
                    if not isinstance(segment.get(field, ""), str):
                        raise ValueError
                a, b = segment["start"], segment["end"]
                if not (math.isfinite(a) and math.isfinite(b) and 0 <= a <= b <= meta["duration"]):
                    raise ValueError
                allowed = ("id", "kind", "start", "end", "text", "speaker", "role")
                saved["segments"][sid] = {k: segment[k] for k in allowed if k in segment}
                if prior.get("topic"):
                    saved["segments"][sid]["topic"] = prior["topic"]
                saved["revision"] += 1
                write_json(folder / "human.json", saved)
            self.reply(json.dumps(saved).encode(), "application/json")
        except PermissionError:
            self.send_error(403)
        except (feedback.Conflict, project_context.Conflict):
            self.send_error(409)
        except (TypeError, KeyError, ValueError, OverflowError):
            self.send_error(400)


def library_projects(library):
    projects = {}
    for manifest in sorted(library.glob("*/project.json")):
        root = manifest.parent.resolve()
        if root.parent == library and (root / "assets").is_dir():
            pid = hashlib.sha256(str(root).encode()).hexdigest()[:20]
            projects[pid] = root
    return projects


def activated_server():
    # launchd holds the listening socket between short-lived workers.
    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    fds = ctypes.POINTER(ctypes.c_int)()
    count = ctypes.c_size_t()
    err = lib.launch_activate_socket(b"Listener", ctypes.byref(fds), ctypes.byref(count))
    if err or count.value != 1:
        raise RuntimeError(f"Cannot obtain launchd listener: {err}, count={count.value}")
    listener = socket.socket(fileno=fds[0])
    lib.free(fds)
    address = listener.getsockname()
    server = ThreadingHTTPServer(address, Review, bind_and_activate=False)
    server.socket.close()
    server.socket = listener
    server.server_port = address[1]
    server.server_name = address[0]
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path, nargs="?")
    parser.add_argument("--activated",action="store_true")
    parser.add_argument("--library", type=Path)
    parser.add_argument("--include", type=Path, action="append", default=[])
    parser.add_argument("--port",type=int,default=0)
    parser.add_argument("--token",default=None)
    args = parser.parse_args()
    if args.project:
        args.project = project_data(args.project)
        read(args.project / "project.json")
    elif not args.library:
        parser.error("需要项目或项目库")
    server = activated_server() if args.activated else ThreadingHTTPServer(("127.0.0.1", args.port), Review)
    server.library = args.library.resolve() if args.library else None
    server.root = args.project or next(iter(library_projects(server.library).values()), server.library)
    server.projects = {}
    for project in filter(None, [args.project, *args.include]):
        root = project_data(project)
        read(root / "project.json")
        pid = hashlib.sha256(str(root).encode()).hexdigest()[:20]
        server.projects[pid] = root
    server.resources = Path(__file__).resolve().parents[1] / "resources"
    server.address = "127.0.0.1:"+str(server.server_port)
    server.token = args.token or secrets.token_urlsafe(24)
    print("http://"+server.address+"/"+server.token+"/", flush=True)
    # Release process memory after a quiet period. Wait for in-flight streams
    # and database writes to finish before leaving.
    import selectors
    server.daemon_threads = False
    with server, selectors.DefaultSelector() as poll:
        poll.register(server.socket, selectors.EVENT_READ)
        while True:
            if poll.select(timeout=30):
                server.handle_request()
            elif not any(thread.is_alive() for thread in server._threads):
                break
