import math
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

WIDTH = 1200
HEIGHT = 630

# 1. Base canvas: obsidian background #09090b
img = Image.new("RGBA", (WIDTH, HEIGHT), (9, 9, 11, 255))

# 2. Luxurious ambient lighting & gradients
ambient = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
ambient_draw = ImageDraw.Draw(ambient)

# Warm gold radial bloom on top right
for r in range(540, 0, -3):
    alpha = int(34 * (1 - (r / 540.0) ** 1.6))
    ambient_draw.ellipse(
        [920 - r, 180 - r, 920 + r, 180 + r],
        fill=(196, 164, 124, alpha)
    )

# Subtle cream/gold glow behind headline on left
for r in range(420, 0, -3):
    alpha = int(22 * (1 - (r / 420.0) ** 1.6))
    ambient_draw.ellipse(
        [260 - r, 280 - r, 260 + r, 280 + r],
        fill=(182, 150, 99, alpha)
    )

img = Image.alpha_composite(img, ambient)
draw = ImageDraw.Draw(img)

# Helper for font selection
def get_font(size, bold=False):
    candidates = []
    if bold:
        candidates = [
            "/System/Library/Fonts/SFNSDisplay-Bold.otf",
            "/System/Library/Fonts/SFProDisplay-Bold.otf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
        ]
    else:
        candidates = [
            "/System/Library/Fonts/SFNSDisplay-Regular.otf",
            "/System/Library/Fonts/SFProDisplay-Regular.otf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()

font_brand = get_font(40, bold=True)
font_badge = get_font(13, bold=True)
font_h1 = get_font(52, bold=True)
font_h1_accent = get_font(52, bold=True)
font_sub = get_font(19, bold=False)
font_pill = get_font(14, bold=True)
font_card_header = get_font(17, bold=True)
font_card_small = get_font(12, bold=False)
font_card_bold = get_font(14, bold=True)
font_meta = get_font(15, bold=False)

# 3. Logo (Bubble icon + crisp white "Vocify")
icon_path = "public/icons/icon-512.png"
if os.path.exists(icon_path):
    icon_src = Image.open(icon_path).convert("RGBA")
    icon_resized = icon_src.resize((58, 58), Image.Resampling.LANCZOS)
    img.paste(icon_resized, (70, 48), icon_resized)
    draw.text((142, 53), "Vocify", font=font_brand, fill=(255, 255, 255, 255))
else:
    draw.text((70, 48), "Vocify", font=font_brand, fill=(255, 255, 255, 255))

# 4. Pill Category Badge (x=70, y=130)
badge_w = 230
badge_h = 32
draw.rounded_rectangle(
    [70, 130, 70 + badge_w, 130 + badge_h],
    radius=16,
    fill=(196, 164, 124, 28),
    outline=(196, 164, 124, 120),
    width=1
)
# Glowing dot inside badge
draw.ellipse([86, 142, 94, 150], fill=(214, 183, 143, 255))
draw.text((102, 138), "AI VOICE-TO-CRM COPILOT", font=font_badge, fill=(230, 205, 170, 255))

# 5. Main Headline (x=70, y=184)
draw.text((70, 184), "Voice to CRM in", font=font_h1, fill=(255, 255, 255, 255))
draw.text((70, 246), "40 Seconds.", font=font_h1_accent, fill=(214, 183, 143, 255))

# 6. Subtitle description (x=70, y=324)
draw.text((70, 324), "Turn field voice notes into structured CRM updates.", font=font_sub, fill=(225, 220, 212, 255))
draw.text((70, 354), "Understands deals, updates HubSpot & Salesforce.", font=font_sub, fill=(160, 155, 148, 255))
draw.text((70, 384), "Zero manual data entry required.", font=font_sub, fill=(160, 155, 148, 255))

# Helper to draw icons
def draw_check_icon(d, cx, cy, color):
    d.line([(cx - 4, cy), (cx - 1, cy + 3), (cx + 5, cy - 3)], fill=color, width=2)

def draw_bolt_icon(d, cx, cy, color):
    points = [(cx + 1, cy - 6), (cx - 4, cy), (cx, cy), (cx - 1, cy + 6), (cx + 4, cy), (cx, cy)]
    d.polygon(points, fill=color)

def draw_dot_icon(d, cx, cy, color):
    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=color)

# 7. Trust / Feature Pills (x=70, y=434)
pills_row1 = [
    ("Instant CRM Sync", "bolt", (30, 26, 22, 240), (196, 164, 124, 130), (230, 210, 180, 255)),
    ("HubSpot & Salesforce", "check", (24, 24, 28, 240), (70, 65, 75, 200), (230, 230, 235, 255)),
]
pills_row2 = [
    ("WhatsApp & Web", "dot", (24, 24, 28, 240), (70, 65, 75, 200), (230, 230, 235, 255)),
    ("GDPR Compliant • EU Data", "check", (20, 28, 22, 240), (50, 90, 60, 200), (190, 230, 200, 255)),
]

curr_x = 70
curr_y = 432
for text, icon_type, bg_fill, border_fill, text_fill in pills_row1:
    bbox = font_pill.getbbox(text)
    tw = bbox[2] - bbox[0]
    pw = tw + 44
    ph = 36
    draw.rounded_rectangle([curr_x, curr_y, curr_x + pw, curr_y + ph], radius=18, fill=bg_fill, outline=border_fill, width=1)
    if icon_type == "bolt":
        draw_bolt_icon(draw, curr_x + 18, curr_y + 18, (214, 183, 143, 255))
    elif icon_type == "check":
        draw_check_icon(draw, curr_x + 18, curr_y + 18, (140, 220, 160, 255))
    draw.text((curr_x + 30, curr_y + 9), text, font=font_pill, fill=text_fill)
    curr_x += pw + 12

curr_x = 70
curr_y = 480
for text, icon_type, bg_fill, border_fill, text_fill in pills_row2:
    bbox = font_pill.getbbox(text)
    tw = bbox[2] - bbox[0]
    pw = tw + 44
    ph = 36
    draw.rounded_rectangle([curr_x, curr_y, curr_x + pw, curr_y + ph], radius=18, fill=bg_fill, outline=border_fill, width=1)
    if icon_type == "dot":
        draw_dot_icon(draw, curr_x + 18, curr_y + 18, (214, 183, 143, 255))
    elif icon_type == "check":
        draw_check_icon(draw, curr_x + 18, curr_y + 18, (140, 220, 160, 255))
    draw.text((curr_x + 30, curr_y + 9), text, font=font_pill, fill=text_fill)
    curr_x += pw + 12

# 8. Domain footer (x=70, y=555)
draw.text((70, 554), "getvocify.com", font=get_font(16, bold=True), fill=(214, 183, 143, 255))
draw.ellipse([186, 563, 190, 567], fill=(100, 95, 90, 255))
draw.text((202, 554), "Stop typing. Start closing.", font=font_meta, fill=(150, 145, 140, 255))

# 9. Right-hand Mockup Card (x=660, y=55, w=470, h=520)
card_x = 660
card_y = 55
card_w = 470
card_h = 520

# Card Shadow
shadow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
s_draw = ImageDraw.Draw(shadow)
s_draw.rounded_rectangle(
    [card_x - 6, card_y + 10, card_x + card_w + 6, card_y + card_h + 20],
    radius=24,
    fill=(0, 0, 0, 180)
)
shadow = shadow.filter(ImageFilter.GaussianBlur(20))
img = Image.alpha_composite(img, shadow)
draw = ImageDraw.Draw(img)

# Card Base Panel
draw.rounded_rectangle(
    [card_x, card_y, card_x + card_w, card_y + card_h],
    radius=20,
    fill=(18, 17, 16, 250),
    outline=(60, 54, 46, 220),
    width=1
)

# Top Section: Voice Memo Waveform Box
vn_y = card_y + 18
draw.rounded_rectangle(
    [card_x + 18, vn_y, card_x + card_w - 18, vn_y + 122],
    radius=14,
    fill=(28, 26, 24, 255),
    outline=(50, 45, 40, 255),
    width=1
)

# Mic icon in gold circle
mic_cx = card_x + 36
mic_cy = vn_y + 24
draw.ellipse([mic_cx - 12, mic_cy - 12, mic_cx + 12, mic_cy + 12], fill=(196, 164, 124, 40), outline=(196, 164, 124, 120))
draw.rounded_rectangle([mic_cx - 3, mic_cy - 6, mic_cx + 3, mic_cy + 2], radius=3, fill=(214, 183, 143, 255))
draw.line([(mic_cx, mic_cy + 2), (mic_cx, mic_cy + 6)], fill=(214, 183, 143, 255), width=2)
draw.line([(mic_cx - 4, mic_cy + 6), (mic_cx + 4, mic_cy + 6)], fill=(214, 183, 143, 255), width=2)

draw.text((card_x + 58, vn_y + 15), "Voice Memo Recording", font=font_card_header, fill=(255, 255, 255, 255))

# Duration badge
draw.rounded_rectangle(
    [card_x + card_w - 82, vn_y + 15, card_x + card_w - 30, vn_y + 35],
    radius=10,
    fill=(196, 164, 124, 35),
    outline=(196, 164, 124, 130),
    width=1
)
draw.text((card_x + card_w - 74, vn_y + 18), "0:34s", font=get_font(12, bold=True), fill=(214, 183, 143, 255))

# Waveform bars
wave_x = card_x + 32
wave_y = vn_y + 56
bars = [6, 12, 22, 34, 16, 26, 40, 46, 32, 20, 38, 44, 28, 18, 36, 48, 38, 20, 30, 42, 26, 14, 28, 40, 24, 16, 8]
for i, bh in enumerate(bars):
    bx = wave_x + i * 15
    by = wave_y + (48 - bh) // 2
    color = (214, 183, 143, 255) if i < 18 else (196, 164, 124, 80)
    draw.rounded_rectangle([bx, by, bx + 6, by + bh], radius=3, fill=color)

# Divider line with AI label
div_y = vn_y + 134
lbl = "AUTOMATED CRM EXTRACTION"
lbl_font = get_font(10, bold=True)
lbl_bbox = lbl_font.getbbox(lbl)
lbl_w = lbl_bbox[2] - lbl_bbox[0]
lbl_x = card_x + (card_w - lbl_w) // 2
draw.line([(card_x + 24, div_y + 6), (lbl_x - 10, div_y + 6)], fill=(55, 48, 42, 255), width=1)
draw.text((lbl_x, div_y), lbl, font=lbl_font, fill=(196, 164, 124, 220))
draw.line([(lbl_x + lbl_w + 10, div_y + 6), (card_x + card_w - 24, div_y + 6)], fill=(55, 48, 42, 255), width=1)

# Extracted Fields Section
fields_y = div_y + 20
draw.rounded_rectangle(
    [card_x + 18, fields_y, card_x + card_w - 18, fields_y + 230],
    radius=14,
    fill=(25, 23, 21, 255),
    outline=(48, 43, 38, 255),
    width=1
)

# Row 1: Contact
r1_y = fields_y + 14
draw.text((card_x + 32, r1_y), "CONTACT & ACCOUNT", font=font_card_small, fill=(140, 134, 126, 255))
draw.text((card_x + 32, r1_y + 18), "Sarah Jenkins", font=font_card_bold, fill=(255, 255, 255, 255))
draw.text((card_x + 142, r1_y + 19), "• VP of Sales, Acme Corp", font=get_font(13, bold=False), fill=(160, 155, 148, 255))

draw.line([(card_x + 32, r1_y + 50), (card_x + card_w - 32, r1_y + 50)], fill=(40, 36, 32, 255), width=1)

# Row 2: Deal & Stage
r2_y = r1_y + 58
draw.text((card_x + 32, r2_y), "DEAL VALUE", font=font_card_small, fill=(140, 134, 126, 255))
draw.text((card_x + 32, r2_y + 18), "€50,000", font=get_font(15, bold=True), fill=(214, 183, 143, 255))

draw.text((card_x + 230, r2_y), "STAGE", font=font_card_small, fill=(140, 134, 126, 255))
draw.text((card_x + 230, r2_y + 18), "Decision Maker Bought-In", font=font_card_bold, fill=(240, 240, 240, 255))

draw.line([(card_x + 32, r2_y + 50), (card_x + card_w - 32, r2_y + 50)], fill=(40, 36, 32, 255), width=1)

# Row 3: Task
r3_y = r2_y + 58
draw.text((card_x + 32, r3_y), "SCHEDULED FOLLOW-UP", font=font_card_small, fill=(140, 134, 126, 255))
draw.text((card_x + 32, r3_y + 18), "Send Enterprise Proposal & Demo Link", font=font_card_bold, fill=(255, 255, 255, 255))
draw.text((card_x + 32, r3_y + 38), "Due next Tuesday at 10:00 AM", font=get_font(12, bold=False), fill=(160, 155, 148, 255))

# Status bottom bar (Instant Sync)
status_y = fields_y + 242
draw.rounded_rectangle(
    [card_x + 18, status_y, card_x + card_w - 18, status_y + 50],
    radius=12,
    fill=(16, 34, 22, 255),
    outline=(30, 80, 44, 255),
    width=1
)
draw.ellipse([card_x + 34, status_y + 20, card_x + 44, status_y + 30], fill=(52, 199, 89, 255))
draw.text((card_x + 52, status_y + 16), "HubSpot & Salesforce Updated", font=get_font(13, bold=True), fill=(220, 250, 230, 255))
draw.text((card_x + card_w - 88, status_y + 17), "0.4s ago", font=get_font(12, bold=False), fill=(140, 200, 160, 255))

# Save 1200x630 OG image
os.makedirs("public/icons", exist_ok=True)
img.save("public/og-image.png", "PNG", optimize=True)
print("Saved public/og-image.png (1200x630)")

# 10. Square 1:1 OG Image (512x512)
sq_size = 512
sq_img = Image.new("RGBA", (sq_size, sq_size), (9, 9, 11, 255))
sq_ambient = Image.new("RGBA", (sq_size, sq_size), (0, 0, 0, 0))
sq_ambient_draw = ImageDraw.Draw(sq_ambient)
for r in range(250, 0, -3):
    alpha = int(35 * (1 - (r / 250.0) ** 1.6))
    sq_ambient_draw.ellipse(
        [256 - r, 220 - r, 256 + r, 220 + r],
        fill=(196, 164, 124, alpha)
    )
sq_img = Image.alpha_composite(sq_img, sq_ambient)
sq_draw = ImageDraw.Draw(sq_img)

if os.path.exists(icon_path):
    icon_sq = Image.open(icon_path).convert("RGBA")
    icon_sq_resized = icon_sq.resize((180, 180), Image.Resampling.LANCZOS)
    sq_img.paste(icon_sq_resized, ((sq_size - 180) // 2, 90), icon_sq_resized)

sq_font_brand = get_font(42, bold=True)
sq_font_sub = get_font(16, bold=False)
sq_font_badge = get_font(13, bold=True)

sq_draw.text(((sq_size - 140) // 2, 290), "Vocify", font=sq_font_brand, fill=(255, 255, 255, 255))
sq_draw.text(((sq_size - 270) // 2, 350), "Voice to CRM in 40 Seconds", font=get_font(18, bold=True), fill=(214, 183, 143, 255))
sq_draw.text(((sq_size - 320) // 2, 385), "AI-Powered Notes for HubSpot & Salesforce", font=sq_font_sub, fill=(160, 155, 148, 255))

# Square Pill
sq_pill_w = 160
sq_draw.rounded_rectangle(
    [(sq_size - sq_pill_w) // 2, 435, (sq_size + sq_pill_w) // 2, 468],
    radius=16,
    fill=(196, 164, 124, 30),
    outline=(196, 164, 124, 120),
    width=1
)
sq_draw.text(((sq_size - 110) // 2, 443), "getvocify.com", font=sq_font_badge, fill=(230, 205, 170, 255))

sq_img.save("public/og-image-square.png", "PNG", optimize=True)
print("Saved public/og-image-square.png (512x512)")

# 11. Complete Favicon set and Apple Touch Icon
if os.path.exists(icon_path):
    base_icon = Image.open(icon_path).convert("RGBA")
    
    # 180x180 Apple Touch Icon (iOS / mobile home screen)
    apple_icon = Image.new("RGBA", (180, 180), (14, 13, 12, 255))
    scaled_icon = base_icon.resize((150, 150), Image.Resampling.LANCZOS)
    apple_icon.paste(scaled_icon, (15, 15), scaled_icon)
    apple_icon.save("public/apple-touch-icon.png", "PNG", optimize=True)
    print("Saved public/apple-touch-icon.png (180x180)")
    
    # 32x32 Favicon PNG
    fav_32 = base_icon.resize((32, 32), Image.Resampling.LANCZOS)
    fav_32.save("public/favicon-32x32.png", "PNG", optimize=True)
    fav_32.save("public/favicon.png", "PNG", optimize=True)
    print("Saved public/favicon-32x32.png and public/favicon.png")
    
    # 16x16 Favicon PNG
    fav_16 = base_icon.resize((16, 16), Image.Resampling.LANCZOS)
    fav_16.save("public/favicon-16x16.png", "PNG", optimize=True)
    print("Saved public/favicon-16x16.png")
    
    # Multi-resolution favicon.ico
    fav_48 = base_icon.resize((48, 48), Image.Resampling.LANCZOS)
    fav_48.save("public/favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print("Saved public/favicon.ico")

if os.path.exists("dist"):
    for f in ["og-image.png", "og-image-square.png", "apple-touch-icon.png", "favicon-32x32.png", "favicon-16x16.png", "favicon.png", "favicon.ico"]:
        src_f = os.path.join("public", f)
        if os.path.exists(src_f):
            Image.open(src_f).save(os.path.join("dist", f))
