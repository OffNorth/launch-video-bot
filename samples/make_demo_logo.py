"""Fabrique un faux logo de démonstration (samples/logo-demo.png) : une tête de grenouille dessinée, pour essayer les styles."""
from PIL import Image, ImageDraw
S = 800
img = Image.new("RGB", (S, S), (24, 28, 36))
d = ImageDraw.Draw(img)
d.ellipse((120, 200, 680, 700), fill=(92, 196, 110))
d.ellipse((150, 120, 370, 340), fill=(92, 196, 110)); d.ellipse((430, 120, 650, 340), fill=(92, 196, 110))
d.ellipse((190, 160, 330, 300), fill="white"); d.ellipse((470, 160, 610, 300), fill="white")
d.ellipse((235, 200, 305, 270), fill=(20, 20, 20)); d.ellipse((515, 200, 585, 270), fill=(20, 20, 20))
d.arc((240, 380, 560, 600), 20, 160, fill=(30, 80, 40), width=18)
d.ellipse((200, 470, 260, 520), fill=(230, 120, 120)); d.ellipse((540, 470, 600, 520), fill=(230, 120, 120))
img.save("samples/logo-demo.png")
