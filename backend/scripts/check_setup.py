"""Health check for the Step 1 environment.

Run from the backend folder:
    python scripts/check_setup.py

It prints a PASS/FAIL line per check and exits with code 1 if anything fails.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))  # so "import app" works from any folder

REQUIRED_PATHS = [
    "app/core/config.py",
    "app/modules/qc/enums.py",
    "app/modules/qc/schemas.py",
    "app/schemas/lesson.py",
    "app/schemas/research.py",
    "tests/unit",
    "../prompts/qc1",
    "../prompts/qc2",
    "../evaluation/benchmark_lessons",
]

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def check_python() -> None:
    v = sys.version_info
    record(
        "Python 3.11 or newer",
        v >= (3, 11),
        f"found {v.major}.{v.minor}.{v.micro}",
    )


def check_packages() -> None:
    for module in ("pydantic", "pydantic_settings", "pytest"):
        try:
            mod = __import__(module)
            record(f"Package '{module}' installed", True, getattr(mod, "__version__", ""))
        except ImportError:
            record(f"Package '{module}' installed", False, "run: pip install -r requirements.txt")


def check_folders() -> None:
    for rel in REQUIRED_PATHS:
        path = (BACKEND_DIR / rel).resolve()
        record(f"Path exists: {rel}", path.exists())


def check_settings() -> None:
    try:
        from app.core.config import ENV_FILE, get_settings

        settings = get_settings()
        record("Settings load without errors", True, f"APP_ENV={settings.app_env}")
        record("MAX_LESSON_MINUTES is 45", settings.max_lesson_minutes == 45,
               f"found {settings.max_lesson_minutes}")
        # Optional in Step 1, so this is information, not a pass/fail check.
        print(f"[INFO] .env file found: {ENV_FILE.exists()} (optional in Step 1; defaults are used if missing)")
        # Never print the key itself. Only report whether one is present.
        print(f"[INFO] LLM key configured: {settings.llm_configured} (not required in Step 1)")
    except Exception as exc:  # noqa: BLE001 - we want to show any problem clearly
        record("Settings load without errors", False, f"{type(exc).__name__}: {exc}")


def check_enums() -> None:
    try:
        from app.modules.qc.enums import ClaimVerdict

        record("QC enums import", True, f"{len(ClaimVerdict)} claim verdicts defined")
    except Exception as exc:  # noqa: BLE001
        record("QC enums import", False, f"{type(exc).__name__}: {exc}")


def check_contracts() -> None:
    try:
        from app.modules.qc.schemas import AuditReport, QCInput, ReleaseResult  # noqa: F401
        from app.schemas.lesson import LessonVersion  # noqa: F401
        from app.schemas.research import ResearchPackage  # noqa: F401

        record("QC data contracts import", True)
    except Exception as exc:  # noqa: BLE001
        record("QC data contracts import", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    check_python()
    check_packages()
    check_folders()
    check_settings()
    check_enums()
    check_contracts()

    failed = [r for r in results if not r[1]]
    print()
    if failed:
        print(f"{len(failed)} check(s) failed. Fix them and run this script again.")
        sys.exit(1)
    print("All required checks passed. Step 1 environment is ready.")
