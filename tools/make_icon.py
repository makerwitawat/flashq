"""สร้าง assets/flashq.ico (สายฟ้าบนพื้นไล่สี) — รันซ้ำได้ ต้องมี Pillow: python tools/make_icon.py"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

S = 1024  # วาดใหญ่แล้วย่อ ให้ขอบเนียน
OUT = Path(__file__).resolve().parent.parent / "assets"


def base() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    px = grad.load()
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * S)  # เฉียงจากฟ้าเข้ม → ม่วง
            px[x, y] = (int(37 + 110 * t), int(99 - 40 * t), int(235 - 20 * t), 255)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((32, 32, S - 32, S - 32), radius=230, fill=255)
    img.paste(grad, (0, 0), mask)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))  # แสงนวลรอบสายฟ้า
    bolt = [(600, 130), (250, 560), (470, 560), (400, 900), (780, 440), (550, 440), (640, 130)]
    ImageDraw.Draw(glow).polygon(bolt, fill=(255, 235, 140, 200))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(38)))
    d = ImageDraw.Draw(img)
    d.polygon(bolt, fill=(255, 214, 64, 255))
    d.line(bolt + [bolt[0]], fill=(255, 250, 220, 255), width=10, joint="curve")
    return img


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    img = base()
    img.save(OUT / "flashq.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.resize((256, 256), Image.LANCZOS).save(OUT / "flashq.png")
    print("OK", OUT / "flashq.ico")
