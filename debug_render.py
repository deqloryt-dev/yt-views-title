# Временный скрипт: пробует разные способы отрисовки, чтобы найти причину обрезки цифр
import glob
import PIL
from PIL import Image, ImageDraw, ImageFont, features

font_path = glob.glob("/usr/share/fonts/**/IBMPlexSans-Regular.*", recursive=True)
print("fonts:", glob.glob("/usr/share/fonts/**/IBMPlexSans-Regular.*", recursive=True))
print("pillow", PIL.__version__, "raqm", features.check("raqm"))
font_path = font_path[0]
lines = ["this video has", "99", "views"]
size, W, H = 175, 1280, 720


def save(name, fn):
    img = Image.new("RGB", (W, H), "white")
    fn(ImageDraw.Draw(img))
    img.save(f"out/{name}.png")


import os
os.makedirs("out", exist_ok=True)
f_raqm = ImageFont.truetype(font_path, size)
f_basic = ImageFont.truetype(font_path, size, layout_engine=ImageFont.Layout.BASIC)
step = size * 1.45
top = H / 2 - step


def mm(font):
    return lambda d: [d.text((W / 2, top + i * step), s, font=font, fill="black", anchor="mm") for i, s in enumerate(lines)]


def baseline(font):
    def f(d):
        for i, s in enumerate(lines):
            asc, desc = font.getmetrics()
            y = top + i * step + size * 0.35
            d.text((W / 2, y), s, font=font, fill="black", anchor="ms")
    return f


for nm, fnt in [("raqm", f_raqm), ("basic", f_basic)]:
    print(nm, "bbox 99 mm:", fnt.getbbox("99", anchor="mm"), "bbox views:", fnt.getbbox("views", anchor="mm"))
    save(f"{nm}_mm", mm(fnt))
    save(f"{nm}_ms", baseline(fnt))
