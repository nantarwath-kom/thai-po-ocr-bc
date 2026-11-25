"""Read a Customer PO (PDF or image) with OpenThai2.1-OCR-Text and shape it into
a Business Central API v2.0 salesOrders request body. Nothing is sent to BC.

Usage: .venv/bin/python po_to_sales_order.py <po.pdf|png|jpg> [out_dir]
Writes <name>.ocr.json (everything read) and <name>.salesOrder.json (spec fields only).
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent / "model"))
from runtime.line_engine import LineOCR  # noqa: E402

# Loose on commas on purpose: OCR returns things like "649,.40".
MONEY = re.compile(r"^-?\d[\d,]*\.\d{2}$")
TOTAL_LABELS = ("Subtotal", "VAT", "Net Total")
LOW_CONFIDENCE = 0.85


def to_num(s):
    return float(s.replace(",", ""))


def is_thai(ch):
    return "\u0e00" <= ch <= "\u0e7f"


def pages(path):
    """PDF -> one PNG per page at 200 dpi (pdftoppm); images pass through."""
    if path.suffix.lower() != ".pdf":
        return [path]
    out = Path(tempfile.mkdtemp())
    subprocess.run(["pdftoppm", "-r", "200", "-png", str(path), str(out / "p")], check=True)
    return sorted(out.glob("p-*.png"))


def group_rows(lines):
    rows = {}
    for ln in lines:
        rows.setdefault(ln["row"], []).append(ln)
    return [sorted(r, key=lambda l: l["box"][0][0]) for _, r in sorted(rows.items())]


def parse_item_row(cells):
    """Cells of one table row, left to right: [#] code description qty unit price discount amount."""
    texts = [c["text"].strip() for c in cells]
    if len(texts) < 6 or not all(MONEY.match(t) for t in texts[-3:]):
        return None
    price, disc, amount = (to_num(t) for t in texts[-3:])
    unit, qty = texts[-4], texts[-5]
    left = cells[:-5]
    if left and left[0]["text"].strip().isdigit() and len(left) > 2:
        left = left[1:]  # line number column; the scan can drop it, so it is optional
    if len(left) < 2 or not qty.replace(",", "").isdigit():
        return None
    return {
        "code": left[0]["text"].strip(),
        "description": " ".join(c["text"].strip() for c in left[1:]),
        "quantity": to_num(qty),
        "unit": unit,
        "unitPrice": price,
        "discountAmount": disc,
        "amount": amount,
        "_descX": left[1]["box"][0][0],
        "_rowH": cells[0]["box"][2][1] - cells[0]["box"][0][1],
        "_lastY": min(c["box"][0][1] for c in cells),
        "_minConfidence": min(c["confidence"] for c in cells),
    }


def read_po(path, ocr):
    po = {"source": path.name, "header": {"buyerName": None}, "lines": [], "totals": {}, "warnings": [], "ocrSeconds": 0.0, "pages": []}
    all_text = []
    for page_no, img in enumerate(pages(path), 1):
        r = ocr.read(str(img))
        all_text.append(r["text"])
        h, w = cv2.imread(str(img)).shape[:2]
        po["pages"].append({"width": w, "height": h, "lines": [
            {"text": ln["text"], "confidence": round(ln["confidence"], 3),
             "box": [round(min(x for x, _ in ln["box"])), round(min(y for _, y in ln["box"])),
                     round(max(x for x, _ in ln["box"])), round(max(y for _, y in ln["box"]))]}
            for ln in r["lines"]]})
        po["ocrSeconds"] += round((r["timing"]["det_ms"] + r["timing"]["rec_ms"]) / 1000, 2)
        if abs(r.get("text_angle", 0)) > 1:
            po["warnings"].append(f"page {page_no}: text tilted {r['text_angle']} degrees (scan?)")
        current = None
        rows = group_rows(r["lines"])
        for i, cells in enumerate(rows[:-1]):
            if page_no == 1 and any("Buyer" in c["text"] for c in cells):
                po["header"]["buyerName"] = rows[i + 1][0]["text"].strip()  # leftmost cell under "Buyer"
        for cells in rows:
            joined = " ".join(c["text"] for c in cells)
            label = next((t for t in TOTAL_LABELS if t in joined), None)
            if label:
                money = [c["text"] for c in cells if MONEY.match(c["text"].strip())]
                if money:
                    po["totals"][label] = to_num(money[-1])
                current = None  # totals block ends the item table
                continue
            top = min(c["box"][0][1] for c in cells)
            item = parse_item_row(cells)
            if item:
                po["lines"].append(item)
                current = item
            elif sum(bool(MONEY.match(c["text"].strip())) for c in cells) >= 2:
                po["warnings"].append(f"page {page_no}: skipped a row that looks like an item: {joined}")
                current = None
            elif current and top - current["_lastY"] < 2.5 * current["_rowH"]:
                # Wrapped cell: text left of the description column continues the item code.
                for c in cells:
                    t = c["text"].strip()
                    if c["box"][0][0] < current["_descX"] - 20:
                        current["code"] += t
                    else:
                        d = current["description"]
                        # Thai has no spaces between words, so a wrapped Thai line joins with nothing.
                        sep = "" if d.endswith("-") or (is_thai(d[-1]) and is_thai(t[0])) else " "
                        current["description"] += sep + t
            else:
                current = None
            if current:
                current["_lastY"] = top
    text = "\n".join(all_text)
    h = po["header"]
    m = re.search(r"No\.\s*(\S+)", text)
    h["poNumber"] = m and m.group(1)
    m = re.search(r"Date\s*(\d{2})/(\d{2})/(\d{4})", text)
    h["orderDate"] = m and f"{m[3]}-{m[2]}-{m[1]}"
    m = re.search(r"Delivery\s*(\d{2})/(\d{2})/(\d{4})", text)
    h["requestedDeliveryDate"] = m and f"{m[3]}-{m[2]}-{m[1]}"
    m = re.search(r"Tax ID:?[\s\S]{0,120}?(\d{13})", text)
    h["buyerTaxId"] = m and m.group(1)
    validate(po)
    return po


def validate(po):
    w = po["warnings"]
    h = po["header"]
    for key in ("poNumber", "orderDate", "buyerTaxId"):
        if not h.get(key):
            w.append(f"header: {key} not found")
    # OCR cannot tell O from 0: flag tokens that mix the letter O with digits.
    if h.get("poNumber") and re.search(r"[0-9][O]|[O][0-9]|P0", h["poNumber"]):
        w.append(f"header: poNumber '{h['poNumber']}' mixes O and 0, check it by eye")
    for i, ln in enumerate(po["lines"], 1):
        expected = round(ln["quantity"] * ln["unitPrice"] - ln["discountAmount"], 2)
        if abs(expected - ln["amount"]) > 0.01:
            w.append(f"line {i} {ln['code']}: {ln['quantity']:g} x {ln['unitPrice']:.2f} - {ln['discountAmount']:.2f} = {expected:.2f}, PO says {ln['amount']:.2f}")
        if ln["_minConfidence"] < LOW_CONFIDENCE:
            w.append(f"line {i} {ln['code']}: low OCR confidence {ln['_minConfidence']:.2f}")
        if len(ln["description"]) > 150:
            w.append(f"line {i} {ln['code']}: description is {len(ln['description'])} chars, BC keeps 100 + 50")
    t = po["totals"]
    if "Subtotal" in t:
        s = round(sum(ln["amount"] for ln in po["lines"]), 2)
        if abs(s - t["Subtotal"]) > 0.01:
            w.append(f"totals: lines add up to {s:,.2f}, PO Subtotal says {t['Subtotal']:,.2f}")
    else:
        w.append("totals: Subtotal not found")
    if {"Subtotal", "VAT", "Net Total"} <= t.keys() and abs(t["Subtotal"] + t["VAT"] - t["Net Total"]) > 0.01:
        w.append("totals: Subtotal + VAT does not equal Net Total")


def to_sales_order(po):
    """Only fields from the API v2.0 salesOrder / salesOrderLine spec."""
    h = po["header"]
    return {
        "customerNumber": None,  # not on the PO; map buyerTaxId to a BC customer before sending
        "externalDocumentNumber": h["poNumber"],
        "orderDate": h["orderDate"],
        "requestedDeliveryDate": h["requestedDeliveryDate"],
        "salesOrderLines": [
            {
                "lineType": "Item",
                "lineObjectNumber": ln["code"],  # the customer's code; BC may not know it
                "description": ln["description"][:100],
                "description2": ln["description"][100:150],
                "unitOfMeasureCode": ln["unit"],
                "quantity": ln["quantity"],
                "unitPrice": ln["unitPrice"],
                "discountAmount": ln["discountAmount"],  # the PO prints baht, not percent
            }
            for ln in po["lines"]
        ],
    }


def main():
    src = Path(sys.argv[1])
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "out")
    out.mkdir(exist_ok=True)
    po = read_po(src, LineOCR(str(Path(__file__).parent / "model"), threads=1))
    for ln in po["lines"]:
        for k in ("_descX", "_rowH", "_lastY"):
            ln.pop(k)
    (out / f"{src.stem}.ocr.json").write_text(json.dumps(po, ensure_ascii=False, indent=2))
    (out / f"{src.stem}.salesOrder.json").write_text(json.dumps(to_sales_order(po), ensure_ascii=False, indent=2))
    print(f"{src.name}: {len(po['lines'])} lines, {len(po['warnings'])} warnings, OCR {po['ocrSeconds']:.2f}s")
    for w in po["warnings"]:
        print("  !", w)


if __name__ == "__main__":
    main()
