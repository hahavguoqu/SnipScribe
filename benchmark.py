import env
import json
import statistics
import time
import argparse
from PIL import Image

parser = argparse.ArgumentParser(description='Benchmark formula recognition on a local image')
parser.add_argument('image', help='Path to a formula screenshot')
args = parser.parse_args()
start = time.perf_counter()
model = env.create_model()
load = time.perf_counter() - start
image = Image.open(args.image).convert('RGB')
import numpy as np
image = np.asarray(image)
runs = []
for i in range(7):
    latex, elapsed = env.recognize(model, image)
    runs.append(elapsed)
    print(f'Run {i}: {elapsed:.3f}s {latex}', flush=True)
report = {'model': 'PP-FormulaNet_plus-S', 'device': 'cpu', 'threads': env.THREADS,
          'load_seconds': load, 'warmup_seconds': runs[0],
          'runs_seconds': runs[1:], 'median_seconds': statistics.median(runs[1:]),
          'max_seconds': max(runs[1:]), 'latex': latex}
(env.ROOT / 'data/benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
