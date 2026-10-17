"""Render self-contained, deterministic chamber-logic GIFs; never run experiments."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageSequence

OUT = Path(__file__).resolve().parent
W, H = 1200, 860
BG, INK, MUTED = '#F3F6FA', '#172B45', '#60738B'
LINE, WHITE = '#DCE4EE', '#FFFFFF'
COLORS = {'P1': '#2465B4', 'P2': '#14877E', 'P3': '#9252A2', 'D': '#BA7416'}
PALE = {'P1': '#E3EDFC', 'P2': '#DDF3EE', 'P3': '#F1E5F5', 'D': '#FFF0D6'}
CX, CY = 335, 350
FONT_PATH = Path('C:/Windows/Fonts/msyh.ttc')
if not FONT_PATH.exists():
    raise RuntimeError('Chinese font missing: set FONT_PATH to an installed CJK font.')
FONTS = {s: ImageFont.truetype(str(FONT_PATH), s) for s in (16, 18, 20, 22, 24, 28, 34, 42)}


def text(d, xy, value, size=22, fill=INK, anchor=None):
    d.text(xy, value, font=FONTS[size], fill=fill, anchor=anchor)


def box(d, bounds, fill=WHITE, outline=LINE, radius=18, width=1):
    d.rounded_rectangle(bounds, radius, fill, outline, width)


def arrow(d, start, end, fill=MUTED, width=3):
    d.line([start, end], fill=fill, width=width)
    a = math.atan2(end[1]-start[1], end[0]-start[0])
    d.polygon([end, (end[0]-12*math.cos(a-.45), end[1]-12*math.sin(a-.45)),
               (end[0]-12*math.cos(a+.45), end[1]-12*math.sin(a+.45))], fill=fill)


def events(mode):
    def ev(kind, title, note, pair=None):
        return dict(kind=kind, title=title, note=note, pair=pair)
    if mode == '4x1':
        return [
            ev('load', '装入第一对 P1', 'P1 的两片产品进入前侧工位。', 'P1'),
            ev('rotate', '半周旋转 · 180°', 'P1 转到后侧，前侧空出。'),
            ev('load', '装入第二对 P2', '四工位满片，具备加工条件。', 'P2'),
            ev('process', '四片同步加工', 'P1、P2 同时完成唯一一次加工。'),
            ev('unload', '先卸出 P2', '后装先卸；P2 已完成加工。', 'P2'),
            ev('rotate', '半周旋转 · 180°', 'P1 转到机械手可访问的前侧。'),
            ev('unload', '再卸出 P1', 'P1 完成退出，腔室恢复空闲。', 'P1'),
            ev('done', '本批加工完成', '4 片产品，每片完成 1 次加工。'),
        ]
    e = [ev('load', '链首：装入辅助对 D', 'D 含两片辅助晶圆，用于补位。', 'D'),
         ev('rotate', '半周旋转 · 180°', 'D 转到后侧，前侧空出。'),
         ev('load', '装入产品对 P1', '链首四工位满片：D + P1。', 'P1'),
         ev('process', '周期 1：D + P1', 'P1 第 1 次曝光；D 保持满片。')]
    for old, new, retained, cycle in [('D', 'P2', 'P1', 2), ('P1', 'P3', 'P2', 3), ('P2', 'D', 'P3', 4)]:
        e += [ev('rotate', '半周旋转 · 180°', f'{retained} 保留并转到后侧；{old} 转到前侧。'),
              ev('unload', f'卸出 {old}', '辅助对返回存储，待链尾再次借用。' if old == 'D' else f'{old} 已完成两次曝光，可以退出。', old),
              ev('load', f'装入 {new}', '链尾借回辅助对 D，补齐四工位。' if new == 'D' else f'{new} 进入前侧，与 {retained} 同时加工。', new),
              ev('process', f'周期 {cycle}：{retained} + {new}', f'{retained} 第 2 次曝光' + ('；D 保持满片。' if new == 'D' else f'；{new} 第 1 次曝光。'))]
    return e + [ev('unload', '链尾：卸出辅助对 D', 'D 返回辅助存储，产品 P3 留在后侧。', 'D'),
                ev('rotate', '半周旋转 · 180°', 'P3 转到前侧，准备退出。'),
                ev('unload', '卸出最后一对 P3', 'P3 已完成两次曝光，腔室清空。', 'P3'),
                ev('done', '整条加工链完成', '6 片产品，每片完成 2 次连续曝光。')]


def initial(mode):
    products = ['P1', 'P2'] if mode == '4x1' else ['P1', 'P2', 'P3']
    return dict(front=None, back=None, coords={}, counts={p: 0 for p in products},
                cycles=[], returned=[], products=products)


def apply(s, e, mode):
    p, kind = e['pair'], e['kind']
    if kind == 'load':
        assert s['front'] is None and p not in s['coords']
        if p != 'D':
            assert s['counts'][p] == 0 and p not in s['returned']
        s['front'] = p
        s['coords'][p] = [(-75, 75), (75, 75)]
    elif kind == 'rotate':
        s['front'], s['back'] = s['back'], s['front']
        s['coords'] = {p: [(-x, -y) for x, y in pts] for p, pts in s['coords'].items()}
    elif kind == 'unload':
        assert s['front'] == p
        if p != 'D':
            assert s['counts'][p] == (1 if mode == '4x1' else 2)
            s['returned'].append(p)
        s['front'] = None
        del s['coords'][p]
    elif kind == 'process':
        assert s['front'] is not None and s['back'] is not None
        pairset = [s['back'], s['front']]
        s['cycles'].append(pairset)
        for p in pairset:
            if p != 'D':
                s['counts'][p] += 1
    else:
        assert not s['coords']
        assert set(s['returned']) == set(s['products'])
    assert len(s['coords']) <= 2


def wafer(d, x, y, p, member, count, target, active=False, progress=0):
    r = 39
    if active:
        d.ellipse((x-r-8, y-r-8, x+r+8, y+r+8), fill='#C9EADF')
        d.arc((x-r-10, y-r-10, x+r+10, y+r+10), -90, -90+360*progress, '#168565', 4)
    d.ellipse((x-r, y-r, x+r, y+r), fill=PALE[p], outline=COLORS[p], width=3)
    d.line((x-7, y+r-2, x+7, y+r-2), fill=COLORS[p], width=3)
    text(d, (x, y-10), f'{p}-{member+1}', 20, COLORS[p], 'mm')
    text(d, (x, y+15), '辅助' if p == 'D' else f'{count}/{target}', 18, COLORS[p], 'mm')


def render(mode, s, e, index, total, t):
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)
    target = 1 if mode == '4x1' else 2
    kind, pair = e['kind'], e['pair']
    finished = t >= 1
    view = copy.deepcopy(s)
    if finished:
        apply(view, e, mode)
    text(d, (38, 22), '4×1  并行加工' if mode == '4x1' else '2×2  链式加工', 42)
    text(d, (40, 82), '四工位旋转腔  /  PW 对 = 两片晶圆  /  每次加工前四工位满片', 22, MUTED)
    box(d, (32, 128, 704, 698))
    box(d, (726, 128, 1168, 320))
    box(d, (726, 336, 1168, 557))
    box(d, (726, 573, 1168, 698))
    text(d, (752, 148), f'步骤 {index+1:02d} / {total:02d}', 18, MUTED)
    text(d, (752, 183), e['title'], 28)
    # Explicit line wrap by measured width, including CJK text.
    lines, line = [], ''
    for char in e['note']:
        if d.textlength(line+char, font=FONTS[20]) > 384:
            lines.append(line); line = ''
        line += char
    lines.append(line)
    for j, line in enumerate(lines):
        text(d, (752, 229+j*30), line, 20, MUTED)
    d.rounded_rectangle((752, 301, 1142, 306), 2, fill=LINE)
    if t > 0:
        d.rounded_rectangle((752, 301, 752+390*t, 306), 2, fill='#2465B4')

    # Chamber top view; front is always the lower, robot-accessible half.
    text(d, (335, 149), '后侧', 18, MUTED, 'mm')
    d.ellipse((CX-185, CY-185, CX+185, CY+185), fill='#F5F8FC', outline='#A4B3C6', width=3)
    d.ellipse((CX-164, CY-164, CX+164, CY+164), outline=LINE, width=2)
    d.line((CX-164, CY, CX+164, CY), fill=LINE, width=2)
    d.ellipse((CX-18, CY-18, CX+18, CY+18), fill='#DCE4EE')
    rotating = kind == 'rotate' and not finished
    angle = math.pi*t if rotating else 0
    for x, y in [(-75, -75), (75, -75), (-75, 75), (75, 75)]:
        xr, yr = x*math.cos(angle)-y*math.sin(angle), x*math.sin(angle)+y*math.cos(angle)
        d.ellipse((CX+xr-41, CY+yr-41, CX+xr+41, CY+yr+41), outline='#CCD7E4', width=2)
    text(d, (335, 558), '前侧 · VTR 装卸访问侧', 20, MUTED, 'mm')
    text(d, (552, 195), '腔室俯视', 18, MUTED)
    text(d, (552, 228), '占位', 18, MUTED)
    occupied = len(view['coords'])*2
    text(d, (552, 255), f'{occupied} / 4', 28)
    if kind == 'process':
        text(d, (552, 305), '同步加工', 20, '#168565')
        text(d, (552, 338), '180 s' if mode == '4x1' else '90 s', 24, '#168565')
        text(d, (552, 372), '名义时长', 16, MUTED)
    if kind == 'rotate':
        d.arc((CX-178, CY-178, CX+178, CY+178), 205, 310, '#2465B4', 5)
        text(d, (552, 323), f'{round(180*t)}°', 28, '#2465B4')
    # Pair loading/unloading has a single access path, no teleporting through back.
    positions = copy.deepcopy(view['coords'] if finished else s['coords'])
    moving = []
    if rotating:
        positions = {p: [(x*math.cos(angle)-y*math.sin(angle), x*math.sin(angle)+y*math.cos(angle))
                         for x, y in pts] for p, pts in positions.items()}
    if kind in ('load', 'unload'):
        text(d, (335, 681), 'VTR 成对搬运 · 腔外供回片示意', 18, MUTED, 'mm')
        if kind == 'load':
            arrow(d, (445, 641), (445, 578), COLORS[pair])
            if not finished:
                moving = [(CX+x, 625+(CY+75-625)*t) for x in (-75, 75)]
        else:
            arrow(d, (445, 578), (445, 641), COLORS[pair])
            positions.pop(pair, None)
            moving = [(CX+x, CY+y+(625-CY-y)*t) for x, y in s['coords'][pair]]
    else:
        text(d, (335, 626), '加工 / 旋转 / 装卸分阶段执行', 20, MUTED, 'mm')
    for p, pts in positions.items():
        for member, (x, y) in enumerate(pts):
            wafer(d, CX+x, CY+y, p, member, view['counts'].get(p, 0), target,
                  kind == 'process', t)
    for member, (x, y) in enumerate(moving):
        wafer(d, x, y, pair, member, view['counts'].get(pair, 0), target)

    text(d, (752, 355), '产品加工进度', 24)
    text(d, (1138, 361), '每对含 2 片', 18, MUTED, 'ra')
    for j, p in enumerate(s['products']):
        y = 402+j*45
        d.ellipse((752, y+4, 766, y+18), fill=COLORS[p])
        text(d, (780, y), p, 20, COLORS[p])
        n = view['counts'][p]
        for k in range(target):
            box(d, (832+k*42, y+2, 863+k*42, y+26), COLORS[p] if k < n else BG, LINE, 5)
        text(d, (930, y), f'{n}/{target}', 20)
        status = '已退出' if p in view['returned'] else ('已完成' if n == target else ('腔内' if p in view['coords'] else '待进入'))
        text(d, (1040, y), status, 20, MUTED)
    text(d, (752, 590), '本模式的关键逻辑', 22)
    if mode == '4x1':
        text(d, (752, 628), '四片 × 一次；后装先卸。', 20)
        text(d, (752, 659), '产品不足时，以辅助晶圆补满。', 18, MUTED)
    else:
        text(d, (752, 628), '每对连续曝光两次；每次换一对。', 20)
        text(d, (752, 659), 'D：链首 / 链尾补位，不计产品。', 18, MUTED)

    sequence = [['P1', 'P2']] if mode == '4x1' else [['D', 'P1'], ['P1', 'P2'], ['P2', 'P3'], ['P3', 'D']]
    bw = 252 if mode == '2x2' else 500
    x0 = 38 if mode == '2x2' else 350
    for j, ps in enumerate(sequence):
        x = x0+j*(bw+35)
        active = kind == 'process' and len(s['cycles']) == j
        complete = len(view['cycles']) > j
        box(d, (x, 720, x+bw, 784), '#E0F2EB' if active or complete else WHITE,
            '#168565' if active else LINE, 12, 2)
        label = f'周期 {j+1}   ' + ' + '.join(ps)
        text(d, (x+bw/2, 751), label, 22, '#146B54' if complete or active else MUTED, 'mm')
        if j < len(sequence)-1:
            arrow(d, (x+bw+7, 751), (x+bw+28, 751))
    text(d, (38, 806), '工艺逻辑示意 · 非实时比例 · 省略腔外完整路线与等待 · 本例不展示清洁', 18, MUTED)
    text(d, (1163, 809), 'JMS', 18, MUTED, 'ra')
    return im


def generate(mode):
    state, evs, frames, durations, previews, trace = initial(mode), events(mode), [], [], [], []
    for i, e in enumerate(evs):
        before = copy.deepcopy(state)
        steps = 24 if e['kind'] == 'process' else 12
        if e['kind'] == 'done':
            steps = 1
        for k in range(steps+1):
            t = k/steps
            frame = render(mode, before, e, i, len(evs), t)
            frames.append(frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
            durations.append((2600 if e['kind'] == 'done' else 850) if k == steps else 90)
        apply(state, e, mode)
        trace.append(dict(step=i+1, event=e, front=state['front'], back=state['back'], counts=dict(state['counts'])))
        if e['kind'] in ('process', 'done') or (mode == '4x1' and e['kind'] == 'unload'):
            previews.append(frame.copy())
    for p in state['products']:
        occurrences = [i for i, ps in enumerate(state['cycles']) if p in ps]
        assert len(occurrences) == (1 if mode == '4x1' else 2)
        if mode == '2x2':
            assert occurrences[1] == occurrences[0]+1
    expected = [['P1', 'P2']] if mode == '4x1' else [['D', 'P1'], ['P1', 'P2'], ['P2', 'P3'], ['P3', 'D']]
    assert state['cycles'] == expected
    path = OUT / f'mode_{mode}.gif'
    # A common palette allows GIF delta frames to retain the static page cleanly.
    sampler = Image.new('RGB', (600, 430*len(previews)), BG)
    for i, preview in enumerate(previews):
        sampler.paste(preview.resize((600, 430)), (0, i*430))
    palette = sampler.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    frames = [f.convert('RGB').quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True, disposal=1)
    # Decode every encoded frame, checking the file itself as well as the event logic.
    with Image.open(path) as gif:
        assert gif.size == (W, H) and gif.info['loop'] == 0
        actual_duration = 0
        source_index = 0
        for frame in ImageSequence.Iterator(gif):
            frame.load()
            assert ImageChops.difference(frame.convert('RGB'), frames[source_index].convert('RGB')).getbbox() is None, 'GIF compositing changed pixels'
            remaining = frame.info['duration']
            while remaining > 0:
                remaining -= durations[source_index]
                source_index += 1
            assert remaining == 0
            actual_duration += frame.info['duration']
        assert actual_duration == sum(durations)
        encoded_frames = gif.n_frames
    cols, tw, th = 2, 600, 430
    sheet = Image.new('RGB', (cols*tw, math.ceil(len(previews)/cols)*th), BG)
    for i, preview in enumerate(previews):
        sheet.paste(preview.resize((tw, th), Image.Resampling.LANCZOS), ((i%cols)*tw, (i//cols)*th))
    sheet.save(OUT / f'mode_{mode}_preview.png')
    return dict(file=path.name, size=[W, H], frames=encoded_frames, duration_seconds=actual_duration/1000,
                bytes=path.stat().st_size, checks='passed: front-only handling, capacity, full occupancy during processing, product exposure counts, consecutive exposures, empty final chamber, GIF decoding and pixel-exact compositing',
                scope='Illustrative chamber event sequence, not a validated full-tool schedule', trace=trace)


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for mode in ('4x1', '2x2'):
        report[mode] = generate(mode)
        print(json.dumps({k: v for k, v in report[mode].items() if k != 'trace'}, ensure_ascii=True), flush=True)
    (OUT / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
