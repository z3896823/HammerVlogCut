"""Import one whisper.cpp JSON draft for audio.wav on the source timeline."""
import argparse
import json
from pathlib import Path
from prepare import read, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_folder", type=Path)
    parser.add_argument("whisper_json", type=Path)
    args = parser.parse_args()
    folder = args.asset_folder
    meta = read(folder / "asset.json")
    path = folder / "model.json"
    result = read(path)
    if any(s["kind"] == "speech" for s in result["segments"]) or result.get("asr_engine"):
        raise SystemExit("已有转写，请在对话中对照两稿，沿用原句 ID。")
    raw = read(args.whisper_json)
    lines = []
    for i, line in enumerate(raw["transcription"], 1):
        start, end = (line["offsets"][k]/1000 for k in ("from","to"))
        if not 0 <= start <= end or start > meta["duration"]:
            raise ValueError("ASR 时间超出原片范围")
        lines.append(dict(id=f"asr-{i:04d}", kind="speech", start=start, end=min(end,meta["duration"]),
            text=line["text"].strip(), speaker="待核实"))
    result["segments"].extend(lines)
    result["asr_engine"] = {"tool":"whisper.cpp", "model":raw.get("model",{}).get("type"),
                            "language":raw.get("result",{}).get("language")}
    result["asr_status"] = "离线 ASR 分句草稿，待听校" if lines else "离线 ASR 未返回文本，待听校"
    write_json(path, result)


if __name__ == "__main__":
    main()
