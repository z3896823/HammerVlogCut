"""Open the public Finder entry point. launchd handles service activation."""
import subprocess
import sys
from pathlib import Path


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    subprocess.run(["open", str(folder / "index.html")], check=True)
