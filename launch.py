import env
import sys
import traceback

with (env.ROOT / 'logs/startup.log').open('a', encoding='utf-8', buffering=1) as log:
    sys.stdout = log; sys.stderr = log
    try:
        from app import main
        main()
    except Exception:
        traceback.print_exc(file=log)
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, '启动失败。详情见 D:\\FormulaSnip\\logs\\startup.log', 'FormulaSnip', 0x10)
