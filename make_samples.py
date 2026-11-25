"""Render the 7 sample Customer POs to samples/ (HTML -> PDF with headless Chrome).
All companies, Tax IDs and phone numbers are made up. Items are CRONUS demo items.
Usage: .venv/bin/python make_samples.py
"""
import html
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = Path(__file__).parent / "samples"

SAMPLE = {"th": "บริษัท ตัวอย่าง เฟอร์นิเจอร์ จำกัด", "en": "SAMPLE FURNITURE CO., LTD.",
          "addr": "1/1 ถนนตัวอย่าง แขวงตัวอย่าง เขตตัวอย่าง กรุงเทพมหานคร 10000",
          "tax": "0109999999999", "contact": "คุณตัวอย่าง ทดลอง โทร 02-000-0001"}
TEST = {"th": "บริษัท ทดสอบ ไม่มีในระบบ จำกัด", "en": "TEST NOT-IN-SYSTEM CO., LTD.",
        "addr": "1 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110",
        "tax": "0105599999999", "contact": "คุณทดสอบ ระบบ โทร 02-000-0000"}

LONG = ("ANTWERP Conference Table โต๊ะประชุมขนาด 240 x 120 ซม. ท็อปไม้โอ๊คแท้ ขาเหล็กพ่นสีดำด้าน "
        "พร้อมรางเดินสายไฟและช่องเสียบปลั๊ก 4 จุด ประกอบและติดตั้งหน้างานชั้น 12 ห้องประชุมใหญ่ กรุณาส่งก่อน 10:00 น.")

# (code, description, qty, unit price, discount baht, amount printed or None = correct)
SAMPLES = {
    "po-01-happy": (SAMPLE, "PO-2610-001", "16/10/2026", "23/10/2026", [
        ("1896-S", "ATHENS Desk", 2, 649.40, 0, None), ("1900-S", "PARIS Guest Chair, black", 4, 125.10, 0, None),
        ("1908-S", "LONDON Swivel Chair, blue", 3, 123.30, 20, None), ("1928-S", "AMSTERDAM Lamp", 5, 35.60, 0, None)]),
    "po-02-unknown-item": (SAMPLE, "PO-2610-002", "16/10/2026", "30/10/2026", [
        ("CU-DESK-01", "โต๊ะทำงาน ATHENS (รหัสของเรา CU-DESK-01)", 1, 649.40, 0, None),
        ("CU-CHR-BLK", "เก้าอี้รับแขก PARIS สีดำ", 6, 125.10, 0, None),
        ("1920-S", "ANTWERP Conference Table", 1, 420.40, 0, None)]),
    "po-03-wrong-amount": (SAMPLE, "PO-2610-003", "17/10/2026", "-", [
        ("1906-S", "ATHENS Mobile Pedestal", 3, 281.40, 0, None), ("1936-S", "BERLIN Guest Chair, yellow", 10, 150.00, 0, None),
        ("1960-S", "ROME Guest Chair, green", 4, 125.10, 0, 800.00)]),
    "po-04-unknown-customer": (TEST, "TST-2026-0101", "17/10/2026", "-", [
        ("1964-S", "TOKYO Guest Chair, blue", 2, 125.10, 0, None), ("1928-S", "AMSTERDAM Lamp", 2, 35.60, 0, None)]),
    "po-05-multipage": (SAMPLE, "PO-2610-005", "18/10/2026", "31/10/2026", [
        ("1896-S", "ATHENS Desk", 1, 649.40, 0, None), ("1900-S", "PARIS Guest Chair, black", 2, 125.10, 0, None),
        ("1906-S", "ATHENS Mobile Pedestal", 3, 281.40, 0, None), ("1908-S", "LONDON Swivel Chair, blue", 4, 123.30, 0, None),
        ("1920-S", "ANTWERP Conference Table", 1, 420.40, 0, None), ("1925-W", "Conference Bundle 1-6", 1, 122.50, 0, None),
        ("1928-S", "AMSTERDAM Lamp", 6, 35.60, 0, None), ("1929-W", "Conference Bundle 1-8", 1, 151.70, 0, None),
        ("1936-S", "BERLIN Guest Chair, yellow", 8, 125.10, 0, None), ("1953-W", "Guest Section 1", 1, 81.60, 0, None),
        ("1960-S", "ROME Guest Chair, green", 4, 125.10, 0, None), ("1964-S", "TOKYO Guest Chair, blue", 4, 125.10, 0, None),
        ("1965-W", "Conference Bundle 2-8", 1, 151.70, 0, None), ("1968-S", "MEXICO Swivel Chair, black", 2, 123.30, 0, None),
        ("1972-S", "MUNICH Swivel Chair, yellow", 2, 123.30, 0, None)]),
    "po-06-scan": (SAMPLE, "PO-2610-006", "18/10/2026", "-", [
        ("1908-S", "LONDON Swivel Chair, blue", 2, 123.30, 0, None), ("1968-S", "MEXICO Swivel Chair, black", 2, 123.30, 0, None),
        ("1972-S", "MUNICH Swivel Chair, yellow", 2, 123.30, 0, None)]),
    "po-07-long-desc": (SAMPLE, "PO-2610-007", "19/10/2026", "26/10/2026", [
        ("1920-S", LONG, 2, 420.40, 0, None), ("1936-S", "BERLIN Guest Chair, yellow", 8, 125.10, 0, None)]),
}
# po-03 prints the wrong line amount and a Subtotal that matches neither the lines nor itself.
SUBTOTAL_OVERRIDE = {"po-03-wrong-amount": 2500.00}

CSS = """
@page { size: A4; margin: 14mm; }
body { font-family: 'Sarabun', 'Thonburi', sans-serif; font-size: 11pt; color: #000; }
h1 { font-size: 20pt; margin: 0; } .top { display: flex; justify-content: space-between; border-bottom: 2px solid #000; padding-bottom: 6px; }
.right { text-align: right; } .boxes { display: flex; gap: 12px; margin: 12px 0; } .box { flex: 1; border: 1px solid #888; padding: 8px; }
table { width: 100%; border-collapse: collapse; } th, td { border: 1px solid #888; padding: 3px 6px; vertical-align: top; }
th { background: #eee; } td.n { text-align: right; } .totals { width: 50%; margin-left: auto; margin-top: 8px; }
.sign { display: flex; justify-content: space-between; margin-top: 60px; } .sign div { width: 40%; border-top: 1px solid #000; text-align: center; }
.break { page-break-before: always; }
"""


def money(v):
    return f"{v:,.2f}"


def table(rows, start):
    head = ("<tr><th>#</th><th>รหัสสินค้า<br>Item Code</th><th>รายละเอียด / Description</th><th>จำนวน<br>Qty</th>"
            "<th>หน่วย<br>Unit</th><th>ราคา/หน่วย<br>Unit Price</th><th>ส่วนลด<br>Discount</th><th>จำนวนเงิน<br>Amount</th></tr>")
    body = "".join(
        f"<tr><td>{start + i}</td><td>{c}</td><td>{html.escape(d)}</td><td class=n>{q}</td><td>PCS</td>"
        f"<td class=n>{money(p)}</td><td class=n>{money(disc)}</td><td class=n>{money(amt)}</td></tr>"
        for i, (c, d, q, p, disc, amt) in enumerate(rows))
    return f"<table>{head}{body}</table>"


def render(name, buyer, no, date, delivery, lines):
    rows = [(c, d, q, p, disc, printed if printed is not None else round(q * p - disc, 2)) for c, d, q, p, disc, printed in lines]
    sub = SUBTOTAL_OVERRIDE.get(name, round(sum(r[5] for r in rows), 2))
    vat = round(sub * 0.07, 2)
    pages = [rows[:8], rows[8:]] if len(rows) > 8 else [rows]
    out = (f"<div class=top><div><h1>ใบสั่งซื้อ / PURCHASE ORDER</h1>{buyer['th']}<br>{buyer['en']}</div>"
           f"<div class=right>เลขที่ / No. <b>{no}</b><br>วันที่ / Date {date}<br>กำหนดส่ง / Delivery {delivery}</div></div>"
           f"<div class=boxes><div class=box><b>ผู้ซื้อ / Buyer</b><br>{buyer['th']}<br>{buyer['addr']}<br>"
           f"เลขประจำตัวผู้เสียภาษี / Tax ID: <b>{buyer['tax']}</b> · สำนักงานใหญ่ (00000)<br>ผู้ติดต่อ / Contact: {buyer['contact']}</div>"
           f"<div class=box><b>ผู้ขาย / Vendor</b><br>CRONUS International Ltd.<br>5 The Ring, Westminster, London W2 8HG<br><br>"
           f"<b>สถานที่จัดส่ง / Ship-to</b><br>{buyer['addr']}</div></div>")
    out += table(pages[0], 1)
    if len(pages) > 1:
        out += f"<div class=break><b>ใบสั่งซื้อ {no} (ต่อ) หน้า 2/2</b><br><br>{table(pages[1], len(pages[0]) + 1)}</div>"
    out += (f"<table class=totals><tr><td>รวมเงิน / Subtotal</td><td class=n>{money(sub)}</td></tr>"
            f"<tr><td>ภาษีมูลค่าเพิ่ม / VAT 7%</td><td class=n>{money(vat)}</td></tr>"
            f"<tr><td><b>รวมทั้งสิ้น / Net Total</b></td><td class=n><b>{money(sub + vat)}</b></td></tr></table>"
            "<p>เงื่อนไขการชำระเงิน: เครดิต 30 วัน</p>"
            "<div class=sign><div>ผู้สั่งซื้อ / Ordered by</div><div>ผู้อนุมัติ / Approved by</div></div>")
    return f"<!doctype html><meta charset=utf-8><style>{CSS}</style>{out}"


def fake_scan(pdf, jpg):
    """Low-res, tilted, warm-paper copy of page 1: stands in for a phone photo of a printout."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "100", "-png", "-f", "1", "-l", "1", str(pdf), f"{tmp}/p"], check=True)
        img = cv2.imread(next(Path(tmp).glob("p*.png")).as_posix())
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), -2.4, 1.0)
    img = cv2.warpAffine(img, m, (w, h), borderValue=(235, 240, 245))
    img = cv2.GaussianBlur(img, (3, 3), 0)
    img = np.clip(img.astype(np.int16) - np.array([12, 6, 0]) + np.random.default_rng(6).normal(0, 6, img.shape), 0, 255)
    cv2.imwrite(str(jpg), img.astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 70])


def main():
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, args in SAMPLES.items():
            src = Path(tmp) / f"{name}.html"
            src.write_text(render(name, *args))
            pdf = OUT / f"{name}.pdf"
            subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf}", src.as_uri()], check=True, capture_output=True)
            if name == "po-06-scan":
                fake_scan(pdf, OUT / f"{name}.jpg")
                pdf.unlink()
            print("wrote", name)


if __name__ == "__main__":
    main()
