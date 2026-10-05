"""On-demand model process. stdout is JSON IPC; library output goes to stderr."""
import env
import sys
import json
import time
import traceback
import contextlib
import re


def order_items(items):
    """Group neighboring text/inline formulas into lines, then order left to right."""
    rows = []
    for item in sorted(items, key=lambda i: (i['box'][1], i['box'][0])):
        x1, y1, x2, y2 = item['box']
        row = None
        for candidate in reversed(rows):
            overlap = min(y2, candidate['bottom']) - max(y1, candidate['top'])
            if overlap > 0.45 * min(y2 - y1, candidate['bottom'] - candidate['top']):
                row = candidate
                break
        if row is None:
            rows.append({'top': y1, 'bottom': y2, 'items': [item]})
        else:
            row['items'].append(item)
            row['top'] = min(row['top'], y1)
            row['bottom'] = max(row['bottom'], y2)
    output = []
    for row in sorted(rows, key=lambda r: r['top']):
        cells = sorted(row['items'], key=lambda i: i['box'][0])
        parts = []
        for cell in cells:
            value = cell['text'].strip()
            if cell['kind'] == 'formula':
                value = '$' + value + '$' if len(cells) > 1 else '$$\n' + value + '\n$$'
            if parts and re.search(r'[\u3400-\u9fff]$', parts[-1]) and re.match(r'[\u3400-\u9fff]', value):
                parts[-1] += value
            else:
                parts.append(value)
        output.append(' '.join(parts))
    return '\n'.join(output)


class Engine:
    def __init__(self):
        self.formula = None
        self.ocr = None
        self.layout = None

    def load(self, mode, progress=lambda _: None):
        if mode in ('formula', 'mixed') and self.formula is None:
            progress('正在加载公式模型…')
            self.formula = env.create_model()
        if mode in ('text', 'mixed') and self.ocr is None:
            progress('正在加载中英文文字模型…')
            from paddleocr import PaddleOCR
            self.ocr = PaddleOCR(
                text_detection_model_name='PP-OCRv5_mobile_det',
                text_detection_model_dir=str(env.ROOT / 'models/PP-OCRv5_mobile_det_infer'),
                text_recognition_model_name='PP-OCRv5_mobile_rec',
                text_recognition_model_dir=str(env.ROOT / 'models/PP-OCRv5_mobile_rec_infer'),
                use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, text_det_limit_side_len=1280,
                text_det_limit_type='max', text_recognition_batch_size=8,
                device='cpu', cpu_threads=env.THREADS, enable_mkldnn=True,
            )
        if mode == 'mixed' and self.layout is None:
            progress('正在加载文字与公式区域检测模型…')
            from paddleocr import LayoutDetection
            self.layout = LayoutDetection(
                model_name='PP-DocLayout_plus-L',
                model_dir=str(env.ROOT / 'models/PP-DocLayout_plus-L_infer'),
                device='cpu', cpu_threads=env.THREADS, enable_mkldnn=True,
            )

    def text_items(self, image):
        import numpy as np
        result = list(self.ocr.predict(image))[0]
        boxes = result.get('rec_boxes', result.get('rec_polys'))
        items = []
        for text, score, box in zip(result['rec_texts'], result['rec_scores'], boxes):
            if float(score) < 0.35 or not text.strip():
                continue
            box = np.asarray(box)
            if box.ndim == 2:
                coords = [box[:, 0].min(), box[:, 1].min(), box[:, 0].max(), box[:, 1].max()]
            else:
                coords = box.tolist()
            items.append({'kind': 'text', 'text': text, 'score': float(score),
                          'box': [int(v) for v in coords]})
        return items

    def run(self, mode, image, progress=lambda _: None):
        self.load(mode, progress)
        start = time.perf_counter()
        if mode == 'formula':
            latex, elapsed = env.recognize(self.formula, image)
            h, w = image.shape[:2]
            items = [{'kind': 'formula', 'text': latex, 'box': [0, 0, w, h]}]
            return {'text': latex, 'items': items, 'seconds': elapsed}
        if mode == 'text':
            progress('正在识别中英文文字…')
            items = self.text_items(image)
            return {'text': order_items(items), 'items': items, 'seconds': time.perf_counter() - start}
        if mode != 'mixed':
            raise ValueError('Unknown mode: ' + mode)
        progress('正在定位公式区域…')
        layout = list(self.layout.predict(image, threshold=0.25))[0]
        h, w = image.shape[:2]
        regions = []
        for box in layout['boxes']:
            if str(box['label']).lower() not in ('formula', 'equation', 'isolated_formula', 'embedding_formula'):
                continue
            x1, y1, x2, y2 = box['coordinate']
            rect = [max(0, int(x1) - 2), max(0, int(y1) - 2), min(w, int(x2) + 3), min(h, int(y2) + 3)]
            if rect[2] - rect[0] < 5 or rect[3] - rect[1] < 5:
                continue
            # NMS can leave nested formula boxes; keep only the more complete region.
            if any(intersection_ratio(rect, existing) > 0.7 for existing in regions):
                continue
            regions.append(rect)
        masked = image.copy()
        items = []
        for index, rect in enumerate(regions):
            progress(f'正在识别公式 {index + 1} / {len(regions)}…')
            x1, y1, x2, y2 = rect
            latex, _ = env.recognize(self.formula, image[y1:y2, x1:x2].copy())
            items.append({'kind': 'formula', 'text': latex, 'box': rect})
            masked[y1:y2, x1:x2] = 255
        progress('正在识别其余文字并合并结果…')
        items.extend(self.text_items(masked))
        warning = '' if regions else '未检测到公式区域；若遗漏公式，请单独框选并使用公式模式。'
        return {'text': order_items(items), 'items': items, 'seconds': time.perf_counter() - start,
                'formula_count': len(regions), 'warning': warning}


def intersection_ratio(a, b):
    area = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return area / max(1, smaller)


def server():
    channel = sys.stdout
    sys.stdout = sys.stderr
    def emit(payload):
        channel.write(json.dumps(payload, ensure_ascii=False) + '\n')
        channel.flush()
    engine = Engine()
    emit({'type': 'ready'})
    for line in sys.stdin:
        try:
            job = json.loads(line)
            job_id = job['id']
            progress = lambda message: emit({'type': 'progress', 'id': job_id, 'message': message})
            if job['action'] == 'load':
                engine.load(job['mode'], progress)
                emit({'type': 'loaded', 'id': job_id, 'mode': job['mode']})
            else:
                import cv2
                import numpy as np
                path = env.ROOT / 'temp' / job['file']
                if path.resolve().parent != (env.ROOT / 'temp').resolve():
                    raise ValueError('Invalid image path')
                image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError('无法读取截图')
                try:
                    result = engine.run(job['mode'], image, progress)
                finally:
                    path.unlink(missing_ok=True)
                emit({'type': 'result', 'id': job_id, **result})
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            emit({'type': 'error', 'id': locals().get('job_id'), 'message': str(exc)})


if __name__ == '__main__':
    server()
