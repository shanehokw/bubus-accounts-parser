# Statements to Excel

Reads bank, card and e-wallet statement PDFs and produces one Excel sheet in this format:

| DATE | MONTH | SETTLED | ACCOUNT | VALUE | CATEGORY | TYPE | DESCRIPTION (optional) |
|---|---|---|---|---|---|---|---|

Runs entirely on this Mac. Nothing is sent to the internet.

## Start

Double-click `run.command`. The app opens in your browser at http://127.0.0.1:8501.
Close the Terminal window to stop it.

1. Drop in one or more PDFs.
2. Check each file's balance check (✅ / ⚠️).
3. Edit the table: categories, TYPE, Exclude, descriptions. Add Cash rows with the **+** under the table.
4. Click **Download Excel**. Categories you picked are saved as rules for next time (or click **Save rules** to save them without downloading).

## Supported statements

| Statement | ACCOUNT | How it's read | Balance check |
|---|---|---|---|
| Maybank Savings | Maybank | PDF text | Running balance and ending balance |
| Maybank Credit Card | Maybank | PDF text | Previous balance + transactions = statement balance |
| HSBC Savings (Amanah) | HSBC | macOS OCR (text is stored as images) | Running balance and closing balance |
| HSBC Credit Card | HSBC | macOS OCR | Previous balance + transactions = statement balance |
| SC Credit Card | SC CC | PDF text | Previous balance + transactions = new balance |
| RHB Savings | RHB | PDF text | Running balance and C/F balance |
| Ryt Savings (Main Account) | Ryt | PDF text | Running balance and closing balance |
| TNG eWallet | TNG | PDF text | Wallet balance after every transaction |

Not yet supported: Grab (needs a sample statement).

## Rules applied

- VALUE: money out is negative, shown as `(55.13)` in Excel.
- SETTLED: FALSE. TYPE: empty.
- Starting balances: not added as rows (still used for the balance check).
- Skipped: credit card cash rebates; TNG reloads, GO+ daily interest, eWallet Cash Out, GO+ Cash In and Cashback; Ryt daily interest and "From Ryt Pocket" moves.
- DESCRIPTION: the statement's remarks, with reference numbers removed.

## Category rules

Stored in `category_rules.json`: `"text in description": "Category"`. A rule applies when its text
appears in a transaction (spaces and upper/lower case ignored); the longest match wins. Edit the
file in any text editor, or use **Category rules** at the bottom of the app. `Exclude` and
`Starting Balance` are never learned from the table; you can add an `Exclude` rule by hand in
**Category rules**.

## Files

| Path | What |
|---|---|
| `app.py` | The app (Streamlit) |
| `statement_parser/parsers/` | One parser per statement type |
| `statement_parser/ocr/pdf_ocr.swift` | OCR helper using macOS Vision; rebuilt automatically if changed |
| `check_samples.py` | Parses every PDF in `Statement Samples` and prints results: `.venv/bin/python check_samples.py --rows` |
| `.venv`, `.python`, `.tools` | Python 3.12 and libraries, installed in this folder |

## Reinstalling the libraries (needs internet once)

```bash
UV_PYTHON_INSTALL_DIR="$PWD/.python" .tools/bin/uv venv --python 3.12 .venv && .tools/bin/uv pip install --python .venv/bin/python -r requirements.txt
```
