"""Fetch openly licensed (CC0 / CC BY) interior photos from Wikimedia Commons for local testing.
Output goes to tests/samples/ (git-ignored).  Usage: python tests/fetch_samples.py"""
import os, sys, ssl, urllib.parse, urllib.request
import certifi
CTX = ssl.create_default_context(cafile=certifi.where())

UA = "RoomlitTests/1.0"
ROOT = os.path.join(os.path.dirname(__file__), "samples")
# (folder, filename on disk, commons title, width or None for original, licence)
SETS = [
    ("Hotel Room A/Bedroom", f"bed_{i}.jpg", t, 3000, "CC0")
    for i, t in enumerate([
        "Bed in hotel room.jpg", "Bed in hotel room 2.jpg", "Bed in hotel room 3.jpg",
        "Bed in hotel room 4.jpg", "Bed in hotel room 5.jpg", "Bed in hotel room 6.jpg"], 1)
] + [
    ("Hotel Room B", f"room_{i}.jpg", f"GD 廣東 Guangdong 廣州 Guangzhou Huangpu MUSTEL Hotel Knowledge City 單人床 bed room double sigle beds June 2025 R12S {i:02d}.jpg", 3000, "CC0")
    for i in range(2, 7)
] + [
    ("Apartments/Rio", "living_big.jpg", "Living room in apartment of Condomínio do Edifício Zaher, Le Blond, Rio de Janeiro, Brazil.jpg", None, "CC0"),
    ("Apartments/Houseplants", "living_2.jpg", "The living room that needs houseplants.jpg", 3000, "CC0"),
    ("Apartments/Calgary", "airbnb_calgary.jpg", "Calgary East Village Airbnb (38265373866).jpg", 3000, "CC BY-SA 2.0"),
    ("Apartments/Modern", "modern_living.jpg", "Modern living room with stylish furniture and a view of the outdoors in a cozy apartment setting.jpg", 3000, "CC BY 2.0"),
    ("Apartments/Tianhe", "tianhe_bed.jpg", "Bed at Tianhe Hotel in Shenzhen.jpg", 3000, "CC0"),
]
os.makedirs(ROOT, exist_ok=True)
lic = []
for folder, name, title, width, licence in SETS:
    d = os.path.join(ROOT, folder); os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, name)
    if os.path.exists(dst): continue
    url = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(title.replace(" ", "_"))
    if width: url += f"?width={width}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120, context=CTX) as r, open(dst, "wb") as f:
            f.write(r.read())
        print("ok", os.path.relpath(dst, ROOT), os.path.getsize(dst)//1024, "KB")
        lic.append(f"{os.path.relpath(dst, ROOT)} | {licence} | commons.wikimedia.org File:{title}")
    except Exception as e:
        print("FAIL", title[:50], e)
with open(os.path.join(ROOT, "ATTRIBUTION.txt"), "a") as f:
    f.write("\n".join(lic) + "\n")
