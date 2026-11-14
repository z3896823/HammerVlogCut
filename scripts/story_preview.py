"""Save a story timeline for live playback of the original media."""
import argparse
import fcntl
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

from prepare import read, version, write_json


def save_timeline(project, plan, edition):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", edition):
        raise ValueError("版本标识无效")
    library = project / "stories"
    library.mkdir(exist_ok=True)
    manifest = read(project / "project.json")
    source = (project / manifest["source_root"]).resolve()
    elapsed = 0
    for clip in plan["clips"]:
        name = clip["source"]
        asset = read(project / "assets" / manifest["assets"][name] / "asset.json")
        path = (source / name).resolve()
        if source not in path.parents or version(path) != asset["version"]:
            raise ValueError(f"原片版本已改变 {name}")
        if not 0 <= clip["in"] < clip["out"] <= asset["duration"]:
            raise ValueError(f"无效的区间 {name}")
        clip["at"] = round(elapsed, 9)
        elapsed += clip["out"] - clip["in"]
    plan["duration"] = round(elapsed, 9)
    with tempfile.TemporaryDirectory(dir=library, prefix=".timeline-") as work:
        staged = Path(work) / "edition"
        staged.mkdir()
        write_json(staged / "story.json", plan)
        staged.rename(library / edition)


def adjusted_plan(project, base, ranges):
    if not isinstance(base, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", base):
        raise ValueError("编排版本无效")
    library = project / "stories"
    plan = read(library / base / "story.json")
    clips = plan["clips"]
    if not isinstance(ranges, list) or len(ranges) != len(clips):
        raise ValueError("镜头数量与所选版本不一致")
    manifest = read(project / "project.json")
    for clip, pair in zip(clips, ranges):
        if not isinstance(pair, list) or len(pair) != 2 or not all(
            type(v) in (float, int) and math.isfinite(v) for v in pair
        ):
            raise ValueError("入点、出点需要填写有效秒数")
        start, end = pair
        key = manifest["assets"][clip["source"]]
        duration = read(project / "assets" / key / "asset.json")["duration"]
        if not 0 <= start < end <= duration or round((end-start)*25) < 1:
            raise ValueError("请检查镜头范围：" + clip["label"])
        clip.update({"in":start,"out":end})
    return plan


def save_trims(project, base, ranges, removed=None):
    plan = adjusted_plan(project, base, ranges)
    library = project / "stories"
    request = [base, ranges]
    if removed is not None:
        if not isinstance(removed, list) or any(type(i) is not int or not 0 <= i < len(ranges) for i in removed):
            raise ValueError("待移出的镜头无效")
        excluded = set(removed)
        if excluded:
            plan["clips"] = [clip for i, clip in enumerate(plan["clips"]) if i not in excluded]
            request.append(sorted(excluded))
    fingerprint = hashlib.sha256(json.dumps(request).encode()).hexdigest()
    with (library / ".render.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        numbers = [0]
        for existing in library.glob("*/story.json"):
            if read(existing).get("trim_request") == fingerprint:
                return existing.parent.name
            match = re.fullmatch(r"v(\d+)", existing.parent.name)
            if match:
                numbers.append(int(match[1]))
        number = max(numbers)+1
        edition = f"v{number:03}"
        plan.update(version=f"第 {number} 版", parent=base, trim_request=fingerprint)
        save_timeline(project, plan, edition)
        return edition


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project",type=Path)
    parser.add_argument("plan",type=Path)
    parser.add_argument("edition")
    args=parser.parse_args()
    save_timeline(args.project,read(args.plan),args.edition)
