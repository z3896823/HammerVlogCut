"""Project-local review queue. A user-triggered refresh consumes a revision."""
import argparse
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from prepare import project_data, read, write_json


class Conflict(ValueError):
    pass


@contextmanager
def database(project):
    db = sqlite3.connect(project / "review.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS feedback
                (asset TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                 pending TEXT NOT NULL, last_applied TEXT NOT NULL DEFAULT '')""")
            db.execute("""CREATE TABLE IF NOT EXISTS background
                (asset TEXT NOT NULL, revision INTEGER NOT NULL, text TEXT NOT NULL,
                 PRIMARY KEY(asset,revision))""")
            yield db
    finally:
        db.close()


def get(db, key):
    row = db.execute("SELECT revision,pending,last_applied FROM feedback WHERE asset=?", (key,)).fetchone()
    state = dict(row) if row else dict(revision=0, pending="", last_applied="")
    history = [r["text"] for r in db.execute(
        "SELECT text FROM background WHERE asset=? ORDER BY revision", (key,))]
    if not history:
        history = [text for text in (state["last_applied"], state["pending"]) if text]
    return dict(state, history=history)


def save(project, key, revision, note):
    if not isinstance(note, str) or not isinstance(revision, int):
        raise ValueError("需要意见文本和版本号")
    with database(project) as db:
        db.execute("BEGIN IMMEDIATE")
        current = get(db,key)
        if revision != current["revision"]:
            raise Conflict("意见已有更新")
        if not note.strip():
            raise ValueError("背景补充不能为空")
        if not db.execute("SELECT 1 FROM background WHERE asset=?", (key,)).fetchone():
            for i, text in enumerate(current["history"], start=-2):
                db.execute("INSERT INTO background VALUES(?,?,?)", (key,i,text))
        db.execute("INSERT INTO background VALUES(?,?,?)", (key,revision+1,note.strip()))
        db.execute("""INSERT INTO feedback(asset,revision,pending) VALUES(?,?,?)
            ON CONFLICT(asset) DO UPDATE SET revision=excluded.revision,pending=excluded.pending""",
            (key,revision+1,note.strip()))
        return get(db,key)


def stamp(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pending(project):
    assets = read(project / "project.json")["assets"]
    with database(project) as db:
        for name, key in assets.items():
            row = get(db, key)
            if row["pending"]:
                yield dict(source=name, asset=key, revision=row["revision"], pending=row["pending"],
                    background=row["history"], model_stamp=stamp(project/"assets"/key/"model.json"))


def apply(project, key, revision, original, proposed):
    assets = read(project/"project.json")["assets"]
    if key not in assets.values():
        raise ValueError("素材版本已变更")
    folder = project/"assets"/key
    path = folder/"model.json"
    draft = read(proposed)
    duration = read(folder/"asset.json")["duration"]
    ids = set()
    for s in draft["segments"]:
        if (s["id"] in ids or not isinstance(s["text"],str) or
            not 0 <= s["start"] <= s["end"] <= duration):
            raise ValueError("片段格式或时间区间有误")
        ids.add(s["id"])
    for k in ("visual_status", "audio_status", "asr_status"):
        if not isinstance(draft[k], str):
            raise ValueError(k)
    with database(project) as db:
        db.execute("BEGIN IMMEDIATE")
        row = get(db,key)
        if revision != row["revision"] or not row["pending"]:
            raise Conflict("意见已有更新，请重新读取")
        if stamp(path) != original and read(path) != draft:
            raise Conflict("模型稿已有更新，请重新读取")
        write_json(path,draft)
        db.execute("UPDATE feedback SET last_applied=pending,pending='',revision=revision+1 WHERE asset=?", (key,))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("pending").add_argument("project",type=Path)
    edit = sub.add_parser("apply")
    edit.add_argument("project",type=Path)
    edit.add_argument("asset")
    edit.add_argument("revision",type=int)
    edit.add_argument("model_stamp")
    edit.add_argument("proposed_json",type=Path)
    args = parser.parse_args()
    args.project = project_data(args.project)
    if args.action == "pending":
        print(json.dumps(list(pending(args.project)),ensure_ascii=False,indent=2))
    else:
        apply(args.project,args.asset,args.revision,args.model_stamp,args.proposed_json)
