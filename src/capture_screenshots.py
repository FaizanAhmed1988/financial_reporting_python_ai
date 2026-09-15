"""
Automated capture of the live Streamlit dashboard for the project report.

Launches `dashboard/app.py` headlessly, drives it with a real Chromium browser
via Playwright, and writes one PNG per dashboard section to docs/screenshots/.

These are genuine renders of the running application. Nothing is mocked and no
placeholder image is ever written: a section that fails to capture is reported
as a failure and the script exits non-zero.

Capture height note: the browser runs at 1440x900. Before each shot the viewport
is grown to the section's own content height so the capture is not cut off at
the fold, capped at MAX_CAPTURE_HEIGHT so the image stays close enough to
landscape to remain legible when placed two-per-page in the PDF report.

Usage:
    python -m src.capture_screenshots
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
from PIL import Image
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "docs" / "screenshots"
RAW_WORKBOOK = PROJECT_ROOT / "data" / "raw" / "GL_COA_TB_Dummy_Dataset.xlsx"

HOST = "localhost"
PORT = 8501
BASE_URL = f"http://{HOST}:{PORT}"

VIEWPORT = {"width": 1440, "height": 900}
DEVICE_SCALE = 2          # retina capture so the PDF prints sharply
MAX_CAPTURE_HEIGHT = 1600
SERVER_BOOT_TIMEOUT = 120
MIN_BYTES = 20_000        # anything smaller is a blank/broken render


@dataclass
class Section:
    """One dashboard section to capture."""
    sidebar_label: str
    filename: str
    ready_text: str                                  # proves the section rendered
    prepare: Optional[Callable[[Page], None]] = None  # extra interaction before the shot


@dataclass
class Result:
    filename: str
    ok: bool
    detail: str = ""
    size: int = 0


# ── Streamlit server lifecycle ───────────────────────────────────────────────

def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def start_streamlit() -> subprocess.Popen:
    """Launch dashboard/app.py headlessly and wait until it answers."""
    if _port_open(HOST, PORT):
        raise RuntimeError(
            f"Port {PORT} is already in use. Stop the other Streamlit instance "
            f"and re-run, so the capture is guaranteed to hit this app."
        )

    print(f"Starting Streamlit on {BASE_URL} ...")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", str(PROJECT_ROOT / "dashboard" / "app.py"),
            "--server.headless", "true",
            "--server.port", str(PORT),
            "--server.fileWatcherType", "none",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )

    deadline = time.time() + SERVER_BOOT_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"Streamlit exited during start-up (code {proc.returncode}):\n"
                f"{proc.stdout.read() if proc.stdout else ''}"
            )
        if _port_open(HOST, PORT):
            time.sleep(2)  # let the first script run finish
            print("Streamlit is up.")
            return proc
        time.sleep(1)

    stop_streamlit(proc)
    raise RuntimeError(f"Streamlit did not become ready within {SERVER_BOOT_TIMEOUT}s.")


def stop_streamlit(proc: Optional[subprocess.Popen]) -> None:
    if proc is None or proc.poll() is not None:
        return
    print("Stopping Streamlit ...")
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()


# ── Browser helpers ──────────────────────────────────────────────────────────

def _settle(page: Page, extra_ms: int = 1500) -> None:
    """Wait for Streamlit's re-run to finish and the DOM to stop moving."""
    try:
        page.wait_for_selector('[data-testid="stStatusWidget"]', state="detached", timeout=45_000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(extra_ms)


def _select_section(page: Page, label: str) -> None:
    """Click a sidebar navigation option."""
    sidebar = page.locator('section[data-testid="stSidebar"]')
    option = sidebar.get_by_text(label, exact=True).first
    option.wait_for(state="visible", timeout=30_000)
    option.click()
    _settle(page)


def _trim_trailing_blank(path: Path, keep_px: int = 48, min_saving: int = 120) -> None:
    """
    Drop uniform blank padding below the last rendered content.

    A section shorter than the viewport leaves a tall empty strip that would
    shrink the image badly once scaled into the report. Only rows identical to
    the bottom-most row are removed, so no content can be lost.
    """
    with Image.open(path) as img:
        img = img.convert("RGB")
        width, height = img.size
        bottom_row = img.crop((0, height - 1, width, height)).tobytes()
        cut = height
        for y in range(height - 1, 0, -1):
            if img.crop((0, y - 1, width, y)).tobytes() != bottom_row:
                cut = y
                break
        new_height = min(height, cut + keep_px)
        if height - new_height < min_saving:
            return
        img.crop((0, 0, width, new_height)).save(path)


def _capture(page: Page, path: Path) -> int:
    """Grow the viewport to the content height (capped), then shoot."""
    content_height = page.evaluate(
        """() => {
            const el = document.querySelector('[data-testid="stAppViewContainer"]');
            return Math.max(
                el ? el.scrollHeight : 0,
                document.body.scrollHeight,
                document.documentElement.scrollHeight
            );
        }"""
    )
    target = max(VIEWPORT["height"], min(int(content_height) + 40, MAX_CAPTURE_HEIGHT))
    page.set_viewport_size({"width": VIEWPORT["width"], "height": target})
    page.wait_for_timeout(1200)
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=False)
    _trim_trailing_blank(path)
    page.set_viewport_size(VIEWPORT)
    page.wait_for_timeout(400)
    return path.stat().st_size


# ── Section-specific preparation ─────────────────────────────────────────────

def _sample_gl_csv() -> Path:
    """Write the project's own General Ledger out as a CSV for the upload demo."""
    gl = pd.read_excel(RAW_WORKBOOK, sheet_name="General Ledger", skiprows=3)
    gl = gl.dropna(subset=["Account Code"])
    out = Path(tempfile.gettempdir()) / "sample_general_ledger_q1_2026.csv"
    gl.to_csv(out, index=False)
    return out


def _prepare_upload(page: Page) -> None:
    """Upload the real GL so the screenshot shows an actual detection result."""
    csv_path = _sample_gl_csv()
    uploader = page.locator('[data-testid="stFileUploaderDropzoneInput"]').first
    uploader.wait_for(state="attached", timeout=30_000)
    uploader.set_input_files(str(csv_path))
    _settle(page, extra_ms=3000)


def _prepare_controls(page: Page) -> None:
    """Open the AI Anomaly Detection tab — that is the result worth showing."""
    tab = page.get_by_role("tab", name="AI Anomaly Detection").first
    tab.wait_for(state="visible", timeout=30_000)
    tab.click()
    _settle(page, extra_ms=2500)


SECTIONS: list[Section] = [
    Section("Executive Summary", "01_executive_summary.png", "Automated Interpretation"),
    Section("Financial Statements", "02_financial_statements.png", "Profit & Loss Statement"),
    Section("Ratios & Working Capital", "03_ratios_working_capital.png", "Working Capital Analysis"),
    Section("Scenario Analysis", "04_scenario_analysis.png", "FP&A Scenario Modeling"),
    Section("Upload Financial Data", "05_upload_feature.png", "Column Mapping", _prepare_upload),
    Section("Controls & AI", "06_controls_ai.png", "Transactions Flagged by ML"),
]
# Controls & AI is captured last only because the upload above leaves a second
# dataset in session state; the tab itself is independent of capture order.
SECTIONS[-1].prepare = _prepare_controls


def capture_all() -> list[Result]:
    results: list[Result] = []
    proc = None
    try:
        proc = start_streamlit()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(
                viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE
            )
            page = context.new_page()
            page.goto(BASE_URL, wait_until="load", timeout=60_000)
            _settle(page, extra_ms=4000)

            for section in SECTIONS:
                target = OUTPUT_DIR / section.filename
                print(f"\n→ {section.sidebar_label} → {section.filename}")
                try:
                    _select_section(page, section.sidebar_label)
                    if section.prepare is not None:
                        section.prepare(page)
                    page.get_by_text(section.ready_text, exact=False).first.wait_for(
                        state="visible", timeout=45_000
                    )
                    size = _capture(page, target)
                    if size < MIN_BYTES:
                        results.append(Result(
                            section.filename, False,
                            f"image is only {size:,} bytes — likely blank", size))
                        print(f"   FAILED — suspiciously small image ({size:,} bytes)")
                    else:
                        results.append(Result(section.filename, True, "captured", size))
                        print(f"   OK — {size:,} bytes")
                except PlaywrightTimeout as exc:
                    results.append(Result(
                        section.filename, False,
                        f"timeout waiting for '{section.ready_text}': "
                        f"{str(exc).splitlines()[0]}"))
                    print(f"   FAILED — timeout waiting for '{section.ready_text}'")
                except Exception as exc:  # noqa: BLE001 - report, never mask
                    results.append(Result(section.filename, False, f"{type(exc).__name__}: {exc}"))
                    print(f"   FAILED — {type(exc).__name__}: {exc}")

            context.close()
            browser.close()
    finally:
        stop_streamlit(proc)
    return results


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = capture_all()

    print("\n" + "=" * 68)
    print("CAPTURE REPORT")
    print("=" * 68)
    for r in results:
        status = "OK    " if r.ok else "FAILED"
        extra = f"{r.size:,} bytes" if r.ok else r.detail
        print(f"{status}  {r.filename:<34} {extra}")

    failed = [r for r in results if not r.ok]
    missing = [s.filename for s in SECTIONS
               if not any(r.filename == s.filename and r.ok for r in results)]
    print("-" * 68)
    print(f"{len(results) - len(failed)}/{len(SECTIONS)} screenshots captured "
          f"into {OUTPUT_DIR.relative_to(PROJECT_ROOT)}/")
    if failed:
        print("\nThese sections did NOT capture and no placeholder was written:")
        for r in failed:
            print(f"  - {r.filename}: {r.detail}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
