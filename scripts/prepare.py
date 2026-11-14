"""Build a resumable source-time index. Only derived files are written."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def write_json(path, value):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
    os.replace(file.name, path)


def read(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def version(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns]


DATA_DIR = "素材审阅数据"


def library_project(source):
    library = Path(__file__).resolve().parents[2] / "Project"
    return library / source.name


def project_data(path):
    path = path.resolve()
    if (path / "project.json").is_file():
        return path
    central = library_project(path)
    manifest = central / "project.json"
    if manifest.is_file() and (central / read(manifest)["source_root"]).resolve() == path:
        return central
    nested = path / DATA_DIR
    return nested if (nested / "project.json").is_file() else path


def checksum(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def build(path, src, out, previous):
    relative = str(path.relative_to(src))
    stamp = version(path)
    fingerprint = checksum(path)
    key = digest(json.dumps([relative, fingerprint]))
    if previous:
        old_record = out / "assets" / previous / "asset.json"
        if old_record.is_file():
            old = read(old_record)
            if old.get("sha256") == fingerprint or (
                "sha256" not in old and old["version"] == stamp
            ):
                key = previous
    folder = out / "assets" / key
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / "asset.json"
    if record.exists():
        meta = read(record)
        if all((folder / frame["file"]).is_file() for frame in meta["frames"]) and (
            not meta["audio_file"] or (folder / meta["audio_file"]).is_file()
        ):
            if meta.get("sha256") != fingerprint or meta["version"] != stamp:
                meta.update(sha256=fingerprint, version=stamp)
                write_json(record, meta)
            return key

    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams",
        "-show_format", "-of", "json", str(path)]))
    fmt = info["format"]
    duration = float(fmt["duration"])
    streams = info["streams"]
    v = next(s for s in streams if s["codec_type"] == "video" and not s["disposition"]["attached_pic"])
    a = next((s for s in streams if s["codec_type"] == "audio"), None)
    origin = float(fmt.get("start_time", 0))
    step = max(.01, float(v.get("duration") or duration) / 32)
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        directory = Path(tmp)
        # showinfo reports actual decoded PTS after FFmpeg normalizes container start.
        filters = (f"select=isnan(prev_selected_t)+gte(t-prev_selected_t\\,{step}),"
                   "scale=640:640:force_original_aspect_ratio=decrease,showinfo")
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(path), "-map",
               f"0:{v['index']}", "-an", "-vf", filters, "-fps_mode", "vfr",
               "-q:v", "3", str(directory / "%04d.jpg")]
        result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        if result.returncode:
            raise ValueError(result.stderr[-1200:])
        times = [float(t) for t in re.findall(r"\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([\d.eE+-]+)", result.stderr)]
        images = sorted(directory.glob("*.jpg"))
        if not times or len(times) != len(images):
            raise ValueError(f"图片和时间戳不匹配 {path}")
        frames = []
        for number, fraction in enumerate((.08, .36, .64, .92), 1):
            index = round((len(times)-1)*fraction)
            name = f"frame-{number}.jpg"
            (folder / name).write_bytes(images[index].read_bytes())
            frames.append(dict(file=name, t=times[index]))
        audio_file = None
        if a:
            audio_file = "audio.wav"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map",
                f"0:{a['index']}", "-vn", "-af", "aresample=16000:async=1:first_pts=0",
                "-ac", "1", "-c:a", "pcm_s16le", str(directory / audio_file)], check=True)
            os.replace(directory / audio_file, folder / audio_file)
    if version(path) != stamp:
        raise ValueError(f"处理期间原片有变化 {path}")
    write_json(record, dict(id=key, source=relative, version=stamp, sha256=fingerprint, duration=duration,
        container_origin=origin, video_stream=v["index"], audio_stream=a["index"] if a else None,
        codec=v["codec_name"], width=v["width"], height=v["height"], frames=frames, audio_file=audio_file))
    if not (folder / "model.json").exists():
        write_json(folder / "model.json", dict(visual_status="待分析", audio_status="待分析" if a else "无音轨",
            asr_status="待识别" if a else "无音轨", segments=[]))
    return key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("project", type=Path, nargs="?")
    parser.add_argument("--only", nargs="+", help="Exact paths relative to source")
    args = parser.parse_args()
    src = args.source.resolve()
    out = args.project.resolve() if args.project else library_project(src)
    if not src.is_dir() or out == src or (src in out.parents and out != src / DATA_DIR):
        parser.error("需要有效素材目录，项目内的数据目录应为素材审阅数据")
    if not args.project and (src / DATA_DIR / "project.json").is_file() and not (out / "project.json").is_file():
        parser.error("发现旧版审阅数据，请先迁至 MediaReview/Project 并更新原片相对路径")
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".prepare.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = out / "project.json"
        project = read(manifest) if manifest.exists() else dict(schema_version=1, title=src.name, source_root=os.path.relpath(src, out), assets={})
        if (out / project["source_root"]).resolve() != src:
            parser.error("项目已绑定其他素材目录")
        extensions = {".mp4",".mov",".m4v",".mkv",".webm",".avi",".mts",".m2ts"}
        paths = []
        if args.only:
            paths = [src / p for p in args.only]
        else:
            for base, dirs, files in os.walk(src):
                dirs[:] = [name for name in dirs if name != DATA_DIR]
                paths.extend(Path(base) / name for name in files if Path(name).suffix.lower() in extensions)
            paths.sort()
        failed = []
        for path in paths:
            try:
                path = path.resolve()
                relative = str(path.relative_to(src))
                excluded = project.get("excluded", {}).get(relative)
                if excluded and checksum(path) == excluded:
                    continue
                key = build(path, src, out, project["assets"].get(relative))
                project["assets"][relative] = key
                write_json(manifest, project)
            except (ValueError, OSError, KeyError, StopIteration, subprocess.SubprocessError) as error:
                failed.append(f"{path}: {error}")
        if not paths or failed:
            raise SystemExit("\n".join(failed) or "没有视频")


if __name__ == "__main__":
    main()
