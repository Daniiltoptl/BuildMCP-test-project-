"""Pixel-block logo in a red 'bevel + extrusion' style. Usage: python3 logo.py TEXT out.png [scale]"""
import sys
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

def glyph_mask(text, px=19):
    f = ImageFont.truetype(FONT, px)
    w = int(f.getlength(text)) + 4
    im = Image.new("L", (w, px + 6), 0)
    ImageDraw.Draw(im).text((2, 1), text, font=f, fill=255)
    im = im.point(lambda v: 255 if v > 110 else 0)      # hard pixel edges
    return im.crop(im.getbbox())

def render(text, scale=6, depth=3):
    m = glyph_mask(text)
    W, H = m.size
    pad = 3
    out = Image.new("RGBA", (W + pad * 2 + depth, H + pad * 2 + depth), (0, 0, 0, 0))
    px = m.load(); o = out.load()
    for y in range(H):
        for x in range(W):
            if not px[x, y]: continue
            for d in range(depth, 0, -1):                 # extrusion down-right
                X, Y = x + pad + d, y + pad + d
                o[X, Y] = (70, 6, 10, 255)
    for y in range(H):
        for x in range(W):
            if not px[x, y]: continue
            t = y / max(1, H - 1)
            r = int(225 - 95 * t); g = int(22 - 14 * t); b = int(30 - 18 * t)
            top = y == 0 or not px[x, y - 1]
            left = x == 0 or not px[x - 1, y]
            bot = y == H - 1 or not px[x, y + 1]
            if top: r, g, b = 255, 96, 88                  # top highlight
            elif left: r, g, b = min(r + 25, 255), g + 8, b + 8
            elif bot: r, g, b = max(r - 60, 90), 6, 12     # bevel shade
            o[x + pad, y + pad] = (r, g, b, 255)
    return out.resize((out.width * scale, out.height * scale), Image.NEAREST)

if __name__ == "__main__":
    text, path = sys.argv[1], sys.argv[2]
    scale = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    render(text, scale).save(path)
