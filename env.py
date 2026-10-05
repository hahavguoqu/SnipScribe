import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UV = str(ROOT / 'tools/uv.exe') if (ROOT / 'tools/uv.exe').is_file() else shutil.which('uv')
if not UV:
    raise RuntimeError('请先安装 uv，或将 uv.exe 放入 tools 目录。')
for folder in ('logs', 'models'):
    (ROOT / folder).mkdir(exist_ok=True)
for name, folder in {
    'UV_CACHE_DIR': '.uv-cache', 'UV_PYTHON_INSTALL_DIR': 'runtime',
    'PADDLE_HOME': 'data/paddle', 'PADDLE_PDX_CACHE_HOME': 'data/paddlex',
    'HF_HOME': 'data/huggingface', 'MODELSCOPE_CACHE': 'data/modelscope',
    'TEMP': 'temp', 'TMP': 'temp', 'XDG_CACHE_HOME': 'data/cache',
}.items():
    path = ROOT / folder
    path.mkdir(parents=True, exist_ok=True)
    os.environ[name] = str(path)
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['PADDLE_PDX_MODEL_SOURCE'] = 'BOS'
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'
THREADS = int(os.environ.get('FORMULASNIP_THREADS', '2'))

def create_model():
    from paddleocr import FormulaRecognition
    return FormulaRecognition(
        model_name='PP-FormulaNet_plus-S',
        model_dir=str(ROOT / 'models' / 'PP-FormulaNet_plus-S_infer'),
        device='cpu', cpu_threads=THREADS, enable_mkldnn=True,
    )

def recognize(model, image):
    import time
    start = time.perf_counter()
    results = list(model.predict(input=image, batch_size=1))
    elapsed = time.perf_counter() - start
    return results[0]['rec_formula'], elapsed
