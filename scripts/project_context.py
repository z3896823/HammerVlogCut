"""Project background source and its reviewed summary, with revision checks."""
import argparse
import fcntl
import json
from pathlib import Path

from prepare import read, write_json, project_data


class Conflict(ValueError):
    pass


def get(root):
    file = root / "project-background.json"
    if file.exists():
        return read(file)
    return dict(revision=0, raw="", summary="", pending=False)


def update(root, revision, text, *, summary=False):
    if not isinstance(text, str):
        raise ValueError("需要文本")
    text = text.strip()
    with (root / ".project-background.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = get(root)
        if state["revision"] != revision:
            raise Conflict("项目背景已有更新")
        if summary:
            if not text or not state["raw"]:
                raise ValueError("需要背景原文和摘要")
            state.update(summary=text, pending=False)
        elif text != state["raw"]:
            state.update(raw=text, summary="", pending=bool(text))
        else:
            return state
        state["revision"] += 1
        write_json(root / "project-background.json", state)
        return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--summary", type=Path, help="UTF-8 summary file")
    parser.add_argument("--revision", type=int)
    args = parser.parse_args()
    root = project_data(args.project)
    read(root / "project.json")
    state = get(root) if args.summary is None else update(
        root, args.revision, args.summary.read_text(), summary=True)
    print(json.dumps(state, ensure_ascii=False, indent=2))
