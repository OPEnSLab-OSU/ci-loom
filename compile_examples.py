# Helper script for compile-examples workflow
# Will not work properly unless you use it with the workflow or define your arduino-cli path. 
# Uses the arduino-cli compiler to compile all sketches 
# --examples-dir can be passed as an arg to change the default example path (/examples). 
import argparse
import atexit
import os
import re
import signal
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_FQBN = "loom4:samd:adafruit_feather_m0"
DEFAULT_DEPENDENCY_REPORT = "compile_dependencies.md"

# Replace this with your path if you want to run it without the workflow.
ARDUINO_CLI_PATH = None

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
NC = "\033[0m"

USING_RECORD_PATTERN = re.compile(
    r"^Using (?P<kind>library|platform|core) (?P<name>.+?) at version (?P<version>\S+) in folder: .+$"
)
USING_LEGACY_RECORD_PATTERN = re.compile(
    r"^Using (?P<kind>library|platform|core) (?P<name>.+?) in folder: .+ \(legacy\)$"
)
USING_PLATFORM_AT_PATTERN = re.compile(
    r"^Using (?P<kind>platform|core) (?P<name>[^@\s]+)@(?P<version>\S+)\b"
)

ACTIVE_PROCESS: subprocess.Popen[str] | None = None


def terminate_active_process():
    global ACTIVE_PROCESS

    process = ACTIVE_PROCESS
    if process is None or process.poll() is not None:
        ACTIVE_PROCESS = None
        return

    print(f"\n{YELLOW}Terminating active arduino-cli process (PID {process.pid})...{NC}")

    if sys.platform.startswith("win"):
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ACTIVE_PROCESS = None
        return

    try:
        process_group_id = os.getpgid(process.pid)
    except ProcessLookupError:
        ACTIVE_PROCESS = None
        return

    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        ACTIVE_PROCESS = None
        return

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(f"{YELLOW}arduino-cli did not exit promptly; killing process {process.pid}.{NC}")
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
    finally:
        ACTIVE_PROCESS = None


def handle_termination_signal(_signum, _frame):
    terminate_active_process()
    raise KeyboardInterrupt


atexit.register(terminate_active_process)

try:
    signal.signal(signal.SIGINT, handle_termination_signal)
    signal.signal(signal.SIGTERM, handle_termination_signal)
except (AttributeError, ValueError):
    pass


def bundled_arduino_cli_candidates() -> list[Path]:
    candidates: list[Path] = []

    if sys.platform.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("ProgramFiles")
        program_files_x86 = os.environ.get("ProgramFiles(x86)")

        roots = []
        if local_app_data:
            roots.append(Path(local_app_data) / "Programs" / "Arduino IDE")
        if program_files:
            roots.append(Path(program_files) / "Arduino IDE")
        if program_files_x86:
            roots.append(Path(program_files_x86) / "Arduino IDE")

        candidates.extend(
            root / "resources" / "app" / "lib" / "backend" / "resources" / "arduino-cli.exe"
            for root in roots
        )
    elif sys.platform == "darwin":
        candidates.append(
            Path("/Applications/Arduino IDE.app")
            / "Contents"
            / "Resources"
            / "app"
            / "lib"
            / "backend"
            / "resources"
            / "arduino-cli"
        )

    return candidates


def find_bundled_arduino_cli() -> Path | None:
    for candidate in bundled_arduino_cli_candidates():
        if candidate.exists():
            return candidate
    return None


def check_arduino_cli(arduino_cli_path: Path | None = None) -> str:
    configured_path = arduino_cli_path or ARDUINO_CLI_PATH

    if configured_path:
        cli = Path(configured_path)
        if cli.exists():
            return str(cli)
        print(f"{RED}ERROR: arduino-cli not found at: {configured_path}{NC}")
        sys.exit(1)

    cli = shutil.which("arduino-cli")
    if not cli:
        bundled_cli = find_bundled_arduino_cli()
        if bundled_cli:
            print(f"{YELLOW}Using arduino-cli bundled with Arduino IDE: {bundled_cli}{NC}")
            return str(bundled_cli)

        print(f"{RED}ERROR: arduino-cli not found in PATH.{NC}")
        print(
            f"{YELLOW}Set ARDUINO_CLI_PATH, pass --arduino-cli, install Arduino IDE, "
            f"or add arduino-cli to your PATH.{NC}"
        )
        sys.exit(1)
    return cli


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    global ACTIVE_PROCESS

    popen_kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }

    if sys.platform.startswith("win"):
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(
        args,
        **popen_kwargs,
    )
    ACTIVE_PROCESS = process

    try:
        stdout, stderr = process.communicate()
    except KeyboardInterrupt:
        terminate_active_process()
        raise
    finally:
        if ACTIVE_PROCESS is process:
            ACTIVE_PROCESS = None

    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def run_cli_inventory_command(cli: str, args: list[str], title: str):
    print(f"\n{title}")
    print("-" * len(title))

    result = run_command([cli, *args])
    output = (result.stdout + result.stderr).strip()

    if output:
        print(output)
    else:
        print("(no output)")

    if result.returncode != 0:
        print(f"{YELLOW}WARNING: arduino-cli {' '.join(args)} returned {result.returncode}.{NC}")


def print_dependency_inventory(cli: str, fqbn: str):
    print(f"\n{'=' * 38}")
    print("Arduino Dependency Inventory")
    print(f"{'=' * 38}")
    print(f"FQBN: {fqbn}")

    run_cli_inventory_command(cli, ["version"], "arduino-cli version")
    run_cli_inventory_command(cli, ["core", "list"], "Installed cores")
    run_cli_inventory_command(cli, ["lib", "list"], "Installed libraries")
    run_cli_inventory_command(cli, ["board", "details", "--fqbn", fqbn], "Selected board details")


def get_installed_platform_record(cli: str, fqbn: str) -> tuple[str, str, str] | None:
    fqbn_parts = fqbn.split(":")
    if len(fqbn_parts) < 2:
        return None

    platform_id = f"{fqbn_parts[0]}:{fqbn_parts[1]}"
    result = run_command([cli, "core", "list"])

    if result.returncode != 0:
        print(f"{YELLOW}WARNING: unable to read installed core list for dependency report.{NC}")
        return None

    for raw_line in result.stdout.splitlines():
        columns = re.split(r"\s{2,}", raw_line.strip(), maxsplit=3)
        if len(columns) >= 2 and columns[0] == platform_id:
            return ("platform", platform_id, columns[1])

    return None


def clean_dependency_name(name: str) -> str:
    return name.strip().strip("'\"")


def extract_dependency_records(output: str) -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []
    table_kind: str | None = None

    for raw_line in output.splitlines():
        line = raw_line.strip()

        if not line:
            table_kind = None
            continue

        verbose_match = USING_RECORD_PATTERN.match(line) or USING_PLATFORM_AT_PATTERN.match(line)
        if verbose_match:
            records.append(
                (
                    verbose_match.group("kind"),
                    clean_dependency_name(verbose_match.group("name")),
                    verbose_match.group("version"),
                )
            )
            continue

        legacy_match = USING_LEGACY_RECORD_PATTERN.match(line)
        if legacy_match:
            records.append(
                (
                    legacy_match.group("kind"),
                    clean_dependency_name(legacy_match.group("name")),
                    "legacy",
                )
            )
            continue

        if line.startswith("Used library"):
            table_kind = "library"
            continue
        if line.startswith("Used platform"):
            table_kind = "platform"
            continue

        if table_kind:
            columns = re.split(r"\s{2,}", line, maxsplit=2)
            if len(columns) >= 2 and columns[0] and columns[1].lower() != "version":
                records.append((table_kind, clean_dependency_name(columns[0]), columns[1]))

    return records


def format_dependency_report(records: list[tuple[str, str, str]], fqbn: str) -> str:
    unique_records = sorted(
        set(records),
        key=lambda record: (record[0], record[1].lower(), record[2]),
    )

    lines = [
        "# Compile Dependencies",
        "",
        "Formatted aggregate of dependency names and versions selected by arduino-cli while compiling examples.",
        "",
        f"- FQBN: `{fqbn}`",
        "",
        "| Type | Name | Version |",
        "| --- | --- | --- |",
    ]

    if unique_records:
        for kind, name, version in unique_records:
            lines.append(f"| {kind} | `{name}` | `{version}` |")
    else:
        lines.append("| none detected |  |  |")

    lines.append("")
    return "\n".join(lines)


def print_dependency_records(records: list[tuple[str, str, str]], fqbn: str):
    print("\nResolved compile dependencies")
    print("-----------------------------")
    print(format_dependency_report(records, fqbn))


def write_dependency_report(report_path: Path, records: list[tuple[str, str, str]], fqbn: str):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    content = format_dependency_report(records, fqbn)

    if report_path.exists() and report_path.read_text(encoding="utf-8") == content:
        print(f"\nDependency report unchanged: {report_path}")
        return

    report_path.write_text(content, encoding="utf-8")
    print(f"\nWrote dependency report: {report_path}")


def collect_dependency_snapshot(
    cli: str,
    fqbn: str,
    sketch: Path,
) -> tuple[subprocess.CompletedProcess[str], list[tuple[str, str, str]]]:
    print(f"\nCollecting dependency snapshot from {sketch.name}...")

    result = run_command([cli, "compile", "--fqbn", fqbn, "--verbose", str(sketch.parent)])

    combined_output = f"{result.stdout}\n{result.stderr}"
    records: list[tuple[str, str, str]] = []

    platform_record = get_installed_platform_record(cli, fqbn)
    if platform_record:
        records.append(platform_record)

    records.extend(extract_dependency_records(combined_output))
    return result, records


def get_skip_reason(ino: Path) -> str | None:
    """Returns a reason string if the sketch should be skipped, or None if valid."""
    if ino.parent.suffix == ".ino":
        return f"parent folder '{ino.parent.name}' should not have a .ino extension — likely a misnamed directory"
    if ino.stem != ino.parent.name:
        return f"sketch '{ino.name}' must be inside a folder with the same name (expected folder: '{ino.stem}/', got: '{ino.parent.name}/')"
    return None


def compile_examples(
    cli: str,
    examples_dir: Path,
    fqbn: str,
    show_dependencies: bool = False,
    dependency_report: Path | None = None,
    fail_fast: bool = False,
):
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
    dependency_snapshot_result: subprocess.CompletedProcess[str] | None = None
    dependency_snapshot_sketch: Path | None = None
    needs_dependency_snapshot = show_dependencies or dependency_report is not None

    if show_dependencies:
        print_dependency_inventory(cli, fqbn)

    if needs_dependency_snapshot:
        dependency_snapshot_sketch = sketches[0]
        dependency_snapshot_result, dependency_records = collect_dependency_snapshot(
            cli,
            fqbn,
            dependency_snapshot_sketch,
        )

        if show_dependencies:
            print_dependency_records(dependency_records, fqbn)

        if dependency_report:
            write_dependency_report(dependency_report, dependency_records, fqbn)

    print(f"\nCompiling all examples for {fqbn}...\n")

    for sketch in sketches:
        print(f"Compiling {sketch.relative_to(examples_dir.parent)}...")

        if sketch == dependency_snapshot_sketch and dependency_snapshot_result is not None:
            result = dependency_snapshot_result
        else:
            result = run_command([cli, "compile", "--fqbn", fqbn, str(sketch.parent)])

        if result.returncode == 0:
            print(f"{GREEN} PASSED: {sketch.name}{NC}")
            passed += 1
        else:
            if result.stdout:
                print(result.stdout)
            print(result.stderr)
            print(f"{RED} FAILED: {sketch.name}{NC}")
            failed += 1
            if fail_fast:
                print(f"{RED}Stopping after first failed sketch because --fail-fast is enabled.{NC}")
                sys.exit(1)

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
    parser.add_argument("--fqbn", default=DEFAULT_FQBN)
    parser.add_argument("--arduino-cli", type=Path, default=None)
    parser.add_argument("--show-dependencies", action="store_true", dest="show_dependencies")
    parser.add_argument("--dependency-report", nargs="?", const=Path(DEFAULT_DEPENDENCY_REPORT), type=Path, default=None)
    parser.add_argument("--no-dependency-report", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    examples_dir = args.examples_dir.resolve()
    print(f"Looking for sketches in: {examples_dir}")

    if not examples_dir.exists():
        print(f"{RED}ERROR: examples directory not found: {examples_dir}{NC}")
        sys.exit(1)

    cli = check_arduino_cli(args.arduino_cli)

    dependency_report = args.dependency_report
    if args.show_dependencies and dependency_report is None and not args.no_dependency_report:
        dependency_report = Path.cwd() / DEFAULT_DEPENDENCY_REPORT
    elif dependency_report is not None and not dependency_report.is_absolute():
        dependency_report = Path.cwd() / dependency_report

    if args.no_dependency_report:
        dependency_report = None

    try:
        compile_examples(
            cli,
            examples_dir,
            args.fqbn,
            show_dependencies=args.show_dependencies,
            dependency_report=dependency_report,
            fail_fast=args.fail_fast,
        )
    except KeyboardInterrupt:
        terminate_active_process()
        print(f"\n{YELLOW}Interrupted. Active arduino-cli process was terminated.{NC}")
        sys.exit(130)
