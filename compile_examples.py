import subprocess
import sys
import shutil
from pathlib import Path

FQBN = "loom4:samd:adafruit_feather_m0"
EXAMPLES_DIR = Path(__file__).parent / "examples"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
NC = "\033[0m"

def check_arduino_cli():
    cli = shutil.which("arduino-cli")
    if not cli:
        print(f"{RED}ERROR: arduino-cli not found in PATH. Make sure it is installed and available.{NC}")
        sys.exit(1)
    return cli

def get_skip_reason(ino: Path) -> str | None:
    """Returns a reason string if the sketch should be skipped, or None if valid."""
    # Folder named like a .ino file (e.g. Adalogger_i2cSensorsSD.ino/)
    if ino.parent.suffix == ".ino":
        return f"parent folder '{ino.parent.name}' should not have a .ino extension — likely a misnamed directory"
    # Sketch filename doesn't match its parent folder (Arduino convention)
    if ino.stem != ino.parent.name:
        return f"sketch '{ino.name}' must be inside a folder with the same name (expected folder: '{ino.stem}/', got: '{ino.parent.name}/')"
    return None

def compile_examples(cli: str):
    all_inos = list(EXAMPLES_DIR.rglob("*.ino"))

    sketches = []
    for ino in all_inos:
        reason = get_skip_reason(ino)
        if reason:
            print(f"{YELLOW}⚠ Skipping {ino.relative_to(EXAMPLES_DIR.parent)}: {reason}{NC}")
        else:
            sketches.append(ino)

    if not sketches:
        print(f"{RED}No valid sketches found!{NC}")
        sys.exit(1)

    passed = 0
    failed = 0

    print(f"\nCompiling all examples...\n")

    for sketch in sketches:
        print(f"Compiling {sketch.relative_to(EXAMPLES_DIR.parent)}...")
        result = subprocess.run(
            [cli, "compile", "--fqbn", FQBN, str(sketch.parent)],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print(f"{GREEN}✓ PASSED: {sketch.name}{NC}")
            passed += 1
        else:
            print(result.stderr)
            print(f"{RED}✗ FAILED: {sketch.name}{NC}")
            failed += 1

    print(f"\n{'=' * 38}")
    print("Compilation Results:")
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print(f"{'=' * 38}")

    if failed:
        sys.exit(1)

if __name__ == "__main__":
    cli = check_arduino_cli()
    compile_examples(cli)