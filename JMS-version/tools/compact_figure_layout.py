"""Compact figure whitespace and axis labels without changing scientific data."""
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops
from matplotlib.transforms import offset_copy


def inline_time_label(fig, ax, label):
    """Place time and units after the final tick, on the tick-label baseline."""
    ax.set_xlabel(label, fontsize=7.2, ha="left", va="top")
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    last = ax.get_xticklabels()[-1]
    tick_half = last.get_window_extent(renderer).width / 2
    label_width = ax.xaxis.label.get_window_extent(renderer).width
    gap = 4 * fig.dpi / 72
    reserved = tick_half + gap + label_width
    last_tick = ax.get_xticks()[-1]
    xmin, xmax = ax.get_xlim()
    assert xmin == 0 and reserved < ax.bbox.width
    xmax = max(xmax, last_tick / (1 - reserved / ax.bbox.width))
    ax.set_xlim(xmin, xmax)
    x = last_tick / xmax + (tick_half + gap) / ax.bbox.width
    ax.xaxis.set_label_coords(x, 0)
    ax.xaxis.label.set_transform(offset_copy(ax.transAxes, fig=fig, y=-6.5, units="points"))
    fig.canvas.draw()
    label_box = ax.xaxis.label.get_window_extent(fig.canvas.get_renderer())
    assert label_box.x1 <= fig.bbox.x1
    assert not label_box.overlaps(last.get_window_extent(fig.canvas.get_renderer()))
    return {"axis_label_placement": "after final tick on the same line",
            "last_tick": float(last_tick), "display_xlim": [xmin, xmax]}


def crop_vector_figure(path, padding_points=2):
    """Trim vertical margins while preserving the printed drawing/font scale."""
    path = Path(path)
    doc = pymupdf.open(path)
    assert len(doc) == 1
    page = doc[0]
    old_size = [page.rect.width, page.rect.height]
    scale = 4
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    delta = ImageChops.difference(im, Image.new("RGB", im.size, "white")).convert("L")
    bounds = delta.point(lambda value: 255 if value > 4 else 0).getbbox()
    assert bounds
    pad = int(padding_points * scale)
    # Manuscript figures are placed at a fixed width. Trimming their sides would
    # enlarge the drawing again and offset the reduction in printed height.
    pixels = (0, max(0, bounds[1] - pad), im.width,
              min(im.height, bounds[3] + pad))
    crop = pymupdf.Rect(*(value / scale for value in pixels)) & page.rect
    page.set_cropbox(crop)
    after = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    expected = im.crop(pixels)
    assert expected.size == (after.width, after.height)
    assert expected.tobytes() == after.samples, "Cropping changed visible drawing pixels"
    new_size = [page.rect.width, page.rect.height]
    pdf_bytes = doc.tobytes(garbage=4, deflate=True)
    page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False).save(path.with_suffix(".png"))
    path.with_suffix(".svg").write_text(page.get_svg_image(), "utf-8")
    doc.close()
    path.write_bytes(pdf_bytes)
    return {"original_size_points": old_size, "cropped_size_points": new_size,
            "padding_points": padding_points, "horizontal_scale_preserved": True,
            "visible_pixels_unchanged": True}
