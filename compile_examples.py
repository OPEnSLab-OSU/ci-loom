# Helper script for compile-examples workflow
# Will not work properly unless you use it with the workflow or define your arduino-cli path. 
# Uses the arduino-cli compiler to compile all sketches 
# --examples-dir can be passed as an arg to change the default example path (/examples). 
import subprocess
import sys
import shutil
import argparse
from pathlib import Path

FQBN = "loom4:samd:adafruit_feather_m0"

# Replace this with your path if you want to run it without the workflow.
ARDUINO_CLI_PATH = None

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
NC = "\033[0m"

def check_arduino_cli() -> str:
    if ARDUINO_CLI_PATH:
        cli = Path(ARDUINO_CLI_PATH)
        if cli.exists():
            return str(cli)
        print(f"{RED}ERROR: arduino-cli not found at ARDUINO_CLI_PATH: {ARDUINO_CLI_PATH}{NC}")
        sys.exit(1)

    cli = shutil.which("arduino-cli")
    if not cli:
        print(f"{RED}ERROR: arduino-cli not found in PATH.{NC}")
        print(f"{YELLOW}Set ARDUINO_CLI_PATH at the top of this script or add arduino-cli to your PATH.{NC}")
        sys.exit(1)
    return cli

def get_skip_reason(ino: Path) -> str | None:
    """Returns a reason string if the sketch should be skipped, or None if valid."""
    if ino.parent.suffix == ".ino":
        return f"parent folder '{ino.parent.name}' should not have a .ino extension — likely a misnamed directory"
    if ino.stem != ino.parent.name:
        return f"sketch '{ino.name}' must be inside a folder with the same name (expected folder: '{ino.stem}/', got: '{ino.parent.name}/')"
    return None

def compile_examples(cli: str, examples_dir: Path):
    all_inos = list(examples_dir.rglob("*.ino"))

    sketches = []
    for ino in all_inos:
        reason = get_skip_reason(ino)
        if reason:
            print(f"{YELLOW} Skipping {ino.relative_to(examples_dir.parent)}: {reason}{NC}")
        else:
            sketches.append(ino)

    if not sketches:
        print(f"{RED}No valid sketches found! Looked in: {examples_dir}{NC}")
        sys.exit(1)

    passed = 0
    failed = 0

    print(f"\nCompiling all examples...\n")

    for sketch in sketches:
        print(f"Compiling {sketch.relative_to(examples_dir.parent)}...")
        result = subprocess.run(
            [cli, "compile", "--fqbn", FQBN, str(sketch.parent)],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"{GREEN} PASSED: {sketch.name}{NC}")
            passed += 1
        else:
            print(result.stderr)
            print(f"{RED} FAILED: {sketch.name}{NC}")
            failed += 1

    print(f"\n{'=' * 38}")
    print("Compilation Results:")
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print(f"{'=' * 38}")

    if failed:
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples-dir", type=Path, default=Path(__file__).parent / "examples")
    args = parser.parse_args()

    examples_dir = args.examples_dir.resolve()
    print(f"Looking for sketches in: {examples_dir}")

    if not examples_dir.exists():
        print(f"{RED}ERROR: examples directory not found: {examples_dir}{NC}")
        sys.exit(1)

    cli = check_arduino_cli()
    compile_examples(cli, examples_dir)