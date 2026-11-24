"""Install the tested optional voice stack in an independent virtual environment."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable, help="base interpreter (tested: Python 3.14 Windows x64)")
    parser.add_argument("--directory", type=Path, default=Path("outputs/voice-runtime"))
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory == Path(sys.prefix).resolve() or directory == Path(sys.base_prefix).resolve():
        parser.error("Choose a separate voice runtime directory, never the host interpreter environment")
    if directory.exists() and any(directory.iterdir()) and not (directory / "pyvenv.cfg").is_file():
        parser.error("Runtime directory already contains non-venv data; choose an empty directory")
    requirements = Path(__file__).resolve().parent.parent / "requirements-voice-tested.txt"
    subprocess.run([args.python, "-m", "venv", str(directory)], check=True)
    interpreter = directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    # The complete frozen closure is intentional: upstream includes a floating Perth
    # Git dependency; --no-deps prevents resolving that instead of our immutable pin.
    subprocess.run([str(interpreter), "-m", "pip", "install", "--no-deps", "-r", str(requirements)], check=True)
    subprocess.run([str(interpreter), "-m", "pip", "check"], check=True)
    print(f"Voice runtime installed: {interpreter}")
    print("Next: atlas voice doctor --download-model")


if __name__ == "__main__":
    main()
