"""Download the four required models from PaddleX's official BOS host."""
import env
import tarfile
import urllib.request

MODELS = ('PP-FormulaNet_plus-S', 'PP-OCRv5_mobile_det',
          'PP-OCRv5_mobile_rec', 'PP-DocLayout_plus-L')


def main():
    for name in MODELS:
        destination = env.ROOT / 'models' / (name + '_infer')
        if (destination / 'inference.pdiparams').is_file():
            print(name + ': already installed', flush=True)
            continue
        archive = env.ROOT / 'temp' / (name + '.tar')
        url = 'https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/' + name + '_infer.tar'
        print('Downloading ' + name, flush=True)
        urllib.request.urlretrieve(url, archive)
        with tarfile.open(archive) as package:
            package.extractall(env.ROOT / 'models', filter='data')
        archive.unlink()
        if not (destination / 'inference.pdiparams').is_file():
            raise RuntimeError('Incomplete model download: ' + name)
    print('All models are ready.')


if __name__ == '__main__':
    main()
