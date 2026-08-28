'''Build the frozen 8- and 16-wafer Gantt manuscript figures.'''

from pathlib import Path
import subprocess

import matplotlib as mpl
import matplotlib.pyplot as plt
from PIL import Image, ImageChops

JMS = Path(__file__).resolve().parents[1]
SOURCE = JMS / 'results' / 'wafer_multiscale_gantt' / 'gantt'
OUT = Path(__file__).resolve().parent
EDGE = Path(
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
)
RASTER = JMS.parent / '.tmp' / 'gantt_raster'
CASES = {
    8: (('Pure 4x1', 'wafer8_41_clean10_20260826'),
        ('Pure 2x2', 'wafer8_22_clean10_20260826'),
        ('4:4 mixed', 'wafer8_mix_4_4_clean10_20260826')),
    16: (('Pure 4x1', 'wafer16_41_clean10_20260826'),
         ('Pure 2x2', 'wafer16_22_clean10_20260826'),
         ('8:8 mixed', 'wafer16_mix_8_8_clean10_20260826')),
}


def configure():
    mpl.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Microsoft YaHei', 'DejaVu Sans'],
        'font.size': 8.5, 'pdf.fonttype': 42, 'ps.fonttype': 42,
        'figure.facecolor': 'white', 'savefig.facecolor': 'white',
    })


def load_svg(path, width=2600):
    if not EDGE.exists():
        raise FileNotFoundError(EDGE)
    RASTER.mkdir(parents=True, exist_ok=True)
    target = RASTER / f'{path.stem}.png'
    command = [
        str(EDGE), '--headless', '--disable-gpu', '--hide-scrollbars',
        '--force-device-scale-factor=1', '--window-size=2600,2400',
        f'--screenshot={target}', path.resolve().as_uri(),
    ]
    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace', check=False
    )
    if result.returncode or not target.exists():
        raise RuntimeError(result.stdout)
    with Image.open(target) as opened:
        image = opened.convert('RGB')
    difference = ImageChops.difference(
        image, Image.new('RGB', image.size, 'white')
    ).convert('L')
    mask = difference.point(lambda value: 255 if value > 8 else 0)
    bbox = mask.getbbox()
    if bbox:
        image = image.crop((
            max(0, bbox[0] - 10), max(0, bbox[1] - 10),
            min(image.width, bbox[2] + 10),
            min(image.height, bbox[3] + 10),
        ))
    return image


def paths(case_dir):
    stem = case_dir.name
    wafer = case_dir / f'{stem}_gantt.svg'
    resource = case_dir / f'{stem}_resources_gantt.svg'
    if not wafer.exists() or not resource.exists():
        raise RuntimeError(f'Missing Gantt source in {case_dir}')
    return wafer, resource


def compose(size):
    configure()
    fig, axes = plt.subplots(3, 2, figsize=(12.4, 13.6))
    axes[0, 0].set_title(
        'Wafer-level Gantt', fontsize=11, fontweight='bold', pad=10
    )
    axes[0, 1].set_title(
        'Resource-level Gantt', fontsize=11, fontweight='bold', pad=10
    )
    for row, (label, folder) in enumerate(CASES[size]):
        wafer_svg, resource_svg = paths(SOURCE / folder)
        for column, image in enumerate(
            (load_svg(wafer_svg), load_svg(resource_svg))
        ):
            axes[row, column].imshow(image)
            axes[row, column].axis('off')
        axes[row, 0].text(
            -0.035, 0.5, label, transform=axes[row, 0].transAxes,
            rotation=90, ha='right', va='center', fontsize=10,
            fontweight='bold', color='#1F2937'
        )
    fig.suptitle(
        f'{size}-wafer exact schedules under identical equipment timing',
        fontsize=12, fontweight='bold', y=0.995, color='#1F2937'
    )
    fig.subplots_adjust(
        left=0.075, right=0.995, bottom=0.01, top=0.965,
        wspace=0.035, hspace=0.14
    )
    stem = OUT / (
        'fig07_mode_gantt8' if size == 8 else 'fig08_mode_gantt16'
    )
    fig.savefig(
        stem.with_suffix('.pdf'), bbox_inches='tight', pad_inches=0.04
    )
    fig.savefig(
        stem.with_suffix('.png'), dpi=220,
        bbox_inches='tight', pad_inches=0.04
    )
    plt.close(fig)


if __name__ == '__main__':
    for wafer_count in CASES:
        compose(wafer_count)
