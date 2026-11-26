"""Entry point shared by the standalone executable and source builds."""
import argparse
import os
import sys
from pathlib import Path


def run():
    parser = argparse.ArgumentParser(description='DocumentAssistant')
    parser.add_argument('--home', type=Path)
    parser.add_argument('--tray', action='store_true')
    args = parser.parse_args()
    location = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    home = (args.home or Path(os.environ.get('DOCUMENTASSISTANT_HOME', location.parent / 'DocumentAssistant-local'))).resolve()
    home.mkdir(parents=True, exist_ok=True)
    temporary = home / 'tmp'
    temporary.mkdir(exist_ok=True)
    os.environ.update(
        DOCUMENTASSISTANT_HOME=str(home),
        TEMP=str(temporary),
        TMP=str(temporary),
        PYTHONUTF8='1',
        PYTHONDONTWRITEBYTECODE='1',
    )
    from document_assistant.gui import main

    return main(start_in_tray=args.tray)


if __name__ == '__main__':
    raise SystemExit(run())
