"""Create an empty, isolated experiment root using the published configurations."""
import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    destination = args.directory.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'configs').mkdir()
    source = Path(__file__).resolve().parents[1] / 'configs'
    for name in ('full.json', 'dev.json'):
        shutil.copyfile(source / name, destination / 'configs' / name)
    print(f'Created isolated experiment at {destination}')
    print('Next: workforce --config <directory>/configs/full.json fetch')


if __name__ == '__main__':
    main()
