def main() -> None:
    import runpy
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    runpy.run_path(str(root / 'app.py'), run_name='__main__')
