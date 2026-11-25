# Customer PO → OCR → salesOrders JSON

Reads a Customer PO (PDF or image) with [OpenThai2.1-OCR-Text](https://huggingface.co/iapp/OpenThai2.1-OCR-Text-20261118) (v2.1.4) and shapes it into a Business Central API v2.0 `salesOrders` request body. **Nothing is sent to BC.**

Walkthrough, traps and a live viewer of these results: [Thai OCR for Business Central Sales Orders](https://suphero.dev/posts/thai-ocr-business-central-sales-order/).

All sample POs in `samples/` are made up. Companies, Tax IDs and phone numbers are fake. Items are CRONUS demo items.

## Run

Needs Python 3.12 and `pdftoppm` (poppler). Regenerating the samples also needs Google Chrome.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements.txt
.venv/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('iapp/OpenThai2.1-OCR-Text-20261118', revision='v2.1.4', local_dir='model')"
.venv/bin/python test_parse.py
for f in samples/*; do .venv/bin/python po_to_sales_order.py "$f" out; done
```

For each PO you get:

- `out/<name>.ocr.json`: everything that was read, plus warnings.
- `out/<name>.salesOrder.json`: only fields from the API v2.0 `salesOrder` / `salesOrderLine` spec. `customerNumber` is `null` because the PO only has the buyer's name and Tax ID.

`run.txt` is the console output of the last run.

## Files

| File | Job |
|---|---|
| `po_to_sales_order.py` | PDF → PNG (pdftoppm, 200 dpi) → OCR → table rows → validation → JSON |
| `test_parse.py` | Self-check for the row parser and validation |
| `make_samples.py` | Renders the 7 sample POs (HTML → PDF with headless Chrome) |

| Sample | What it tests |
|---|---|
| `po-01-happy` | Clean PO, 20.00 baht discount on one line |
| `po-02-unknown-item` | Customer's own item codes, wrapped across two lines |
| `po-03-wrong-amount` | Line amount and Subtotal printed wrong |
| `po-04-unknown-customer` | Buyer not in CRONUS |
| `po-05-multipage` | 15 lines over 2 pages |
| `po-06-scan` | Low-res, tilted JPEG |
| `po-07-long-desc` | Thai description longer than BC's 100 + 50 characters |

## License

Code: MIT (see `LICENSE`). The OCR model is not in this repo. `model/` is downloaded from Hugging Face and is Apache-2.0, © iApp Technology.
