"""
Limitless — Dev Playground Launcher (development tool, not part of the app)

Runs the real FastAPI app and additionally serves a browser UI at /playground
so you can exercise the whole pipeline (questions -> analyze -> PDF ->
longitudinal) without a frontend developer.

Because the UI is served BY the app, it is same-origin: no CORS middleware
is needed and no application code is modified by this file.

Feature flags are set as environment variables BEFORE app.core.config is
imported (config reads env at import time, and python-dotenv does not
override already-set env vars), so the CLI flags below genuinely take effect.

The playground starts with v2 and every feature flag ON, because that is what
it exists to demonstrate. This is a launcher default only — app/core/config.py
keeps its v1-safe defaults, so production (app.main:app) is unaffected.

Usage:
    python dev_playground.py                       # v2, every flag on (default)
    python dev_playground.py --model v1            # v1 scoring, flags still on
    python dev_playground.py --no-flags            # v2, every flag off
    python dev_playground.py --model v1 --no-flags # production default
    python dev_playground.py --no-validity         # all on except validity
    python dev_playground.py --port 8080

Every flag is also toggleable live from the UI without a restart.

Then open:  http://127.0.0.1:8000/playground
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML_FILE = ROOT / "playground.html"


def _bool_env(value: bool) -> str:
    return "true" if value else "false"


def main() -> int:
    parser = argparse.ArgumentParser(description="Limitless dev playground")
    bool_flag = argparse.BooleanOptionalAction  # gives --x / --no-x
    parser.add_argument("--model", choices=["v1", "v2"], default="v2",
                        help="SCORING_MODEL_VERSION (default: v2)")
    parser.add_argument("--confidence", action=bool_flag, default=True,
                        help="ENABLE_CONFIDENCE_INTERVALS (default: on)")
    parser.add_argument("--validity", action=bool_flag, default=True,
                        help="ENABLE_VALIDITY_CHECKS (default: on)")
    parser.add_argument("--reliable-change", action=bool_flag, default=True,
                        help="ENABLE_RELIABLE_CHANGE (default: on)")
    parser.add_argument("--methodology", action=bool_flag, default=True,
                        help="ENABLE_METHODOLOGY_PAGE (default: on)")
    parser.add_argument("--no-flags", action="store_true",
                        help="Turn every feature flag off (model is unaffected)")
    parser.add_argument("--item-bank", default=None, help="ITEM_BANK_VERSION")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if not HTML_FILE.exists():
        print(f"ERROR: {HTML_FILE.name} not found next to {Path(__file__).name}", file=sys.stderr)
        return 1

    # --- Set flags BEFORE importing the app (config reads env at import time) ---
    on = not args.no_flags  # --no-flags is a blanket override of the per-flag values
    os.environ["SCORING_MODEL_VERSION"] = args.model
    os.environ["ENABLE_CONFIDENCE_INTERVALS"] = _bool_env(on and args.confidence)
    os.environ["ENABLE_VALIDITY_CHECKS"] = _bool_env(on and args.validity)
    os.environ["ENABLE_RELIABLE_CHANGE"] = _bool_env(on and args.reliable_change)
    os.environ["ENABLE_METHODOLOGY_PAGE"] = _bool_env(on and args.methodology)
    if args.item_bank:
        os.environ["ITEM_BANK_VERSION"] = args.item_bank

    sys.path.insert(0, str(ROOT))

    import uvicorn

    from app.main import app          # noqa: E402 — must come after env setup
    from app.core.config import settings  # noqa: E402
    from playground_routes import attach_playground  # noqa: E402

    # Same routes the deployed build serves (see playground_app.py)
    attach_playground(app, HTML_FILE)

    url = f"http://{args.host}:{args.port}/playground"
    print("=" * 66)
    print("  LIMITLESS DEV PLAYGROUND")
    print("=" * 66)
    print(f"  Scoring model ............ {settings.SCORING_MODEL_VERSION}")
    print(f"  Confidence intervals ..... {settings.ENABLE_CONFIDENCE_INTERVALS}")
    print(f"  Validity checks .......... {settings.ENABLE_VALIDITY_CHECKS}")
    print(f"  Reliable change .......... {settings.ENABLE_RELIABLE_CHANGE}")
    print(f"  Methodology page ......... {settings.ENABLE_METHODOLOGY_PAGE}")
    print(f"  Item bank ................ {settings.ITEM_BANK_VERSION}")
    print(f"  Gemini key present ....... {bool(settings.GEMINI_API_KEY)}")
    print("-" * 66)
    print(f"  UI       {url}")
    print(f"  API docs http://{args.host}:{args.port}/docs")
    print("=" * 66)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
