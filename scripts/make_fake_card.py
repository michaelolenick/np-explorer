"""One-off: static/share/fake-vc.png, the link preview for /how-to-spot-a-fake (owner, 2026-10-30)."""
from pathlib import Path
from PIL import Image, ImageDraw
from app.sharecard import _font, REGULAR, BOLD, W, H

out = Path("static/share"); out.mkdir(exist_ok=True)
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
d.rectangle([0, 0, W - 1, H - 1], outline="#c00", width=14)
d.text((72, 70), "HOW TO SPOT", font=_font(BOLD, 64), fill="black")
d.text((72, 150), "A FAKE VC", font=_font(BOLD, 120), fill="#c00")
d.text((72, 300), "Check any fund in a minute:", font=_font(REGULAR, 44), fill="black")
d.text((72, 360), "Form D, Form ADV, broker-dealers,", font=_font(REGULAR, 40), fill="black")
d.text((72, 410), "and everything else on the name.", font=_font(REGULAR, 40), fill="black")
d.line([72, 500, W - 72, 500], fill="black", width=3)
d.text((72, 525), "furp.org/fake", font=_font(BOLD, 52), fill="black")
d.text((W - 72, 540), "free, no login", font=_font(REGULAR, 34), fill="#555", anchor="ra")
img.save(out / "fake-vc.png", optimize=True)
print("ok")
