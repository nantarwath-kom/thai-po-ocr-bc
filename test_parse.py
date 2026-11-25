"""Self-check for the row parser and validation. Run: .venv/bin/python test_parse.py"""
from po_to_sales_order import is_thai, parse_item_row, validate


def cell(text, x, y=100, conf=0.99):
    return {"text": text, "confidence": conf, "box": [[x, y], [x + 50, y], [x + 50, y + 30], [x, y + 30]]}


row = [cell("3", 120), cell("1908-S", 170), cell("LONDON Swivel Chair, blue", 358),
       cell("3", 867), cell("PCS", 910), cell("123.30", 1081), cell("20.00", 1265), cell("349.90", 1421)]
item = parse_item_row(row)
assert item["code"] == "1908-S" and item["quantity"] == 3 and item["discountAmount"] == 20.0, item

# The scan drops the line-number column: the row must still parse.
assert parse_item_row(row[1:])["code"] == "1908-S"
# Header and totals rows are not items.
assert parse_item_row([cell("Unit Price", 1000), cell("Discount", 1200), cell("Amount", 1400)]) is None

po = {"header": {"poNumber": "P0-2610-O02", "orderDate": "2026-10-16", "buyerTaxId": "0105599999999"},
      "lines": [dict(item, amount=500.0)], "totals": {"Subtotal": 2500.0}, "warnings": []}
validate(po)
assert any("mixes O and 0" in w for w in po["warnings"])
assert any("= 349.90, PO says 500.00" in w for w in po["warnings"])
assert any("Subtotal says 2,500.00" in w for w in po["warnings"])
assert is_thai("ก") and not is_thai("A")
print("ok")
