# Community Event Fund Tracker

An AI-assisted app for reviewing community fundraiser transactions and reporting the event's annual finances. Upload a CSV, review or edit categories, and see the 2025 opening reserve, 2026 donations and spending, and the balance carried into 2027.

## Features

- CSV import with required `date`, `description`, and `amount` columns; optional `type` and `category` columns.
- Local keyword category suggestions, with editable categories for human review.
- Optional AI categorization using OpenAI structured JSON output and a confidence score.
- 2026 spending chart grouped by category.
- Deterministic reserve calculation: opening reserves + donations + other income - expenses.
- Downloadable CSV containing the reviewed categories.

## Requirements

- Python 3.10 or newer
- OpenAI API key only if you want to use AI categorization

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

In the sidebar, enter the 2025 opening reserve. Upload a CSV with columns like:

```csv
date,description,amount,type
2026-01-15,GoFundMe donation,250.00,income
2026-02-02,Tent rental,400.00,expense
2026-02-03,Plates and spoons,85.50,expense
```

Try `sample_transactions.csv` for an example upload.

Amounts can be positive with an explicit `type`, or signed when `type` is omitted (positive for income and negative for expenses). Dates must use `YYYY-MM-DD` or `MM/DD/YYYY`. Category suggestions can be changed in the transaction table before the summary is calculated.

Set `OPENAI_API_KEY` before starting Streamlit, or enter the key in the sidebar. The app only sends transaction descriptions and income/expense types to the model for categorization; never upload account numbers or other sensitive information. API usage may incur provider charges.

## Test

```powershell
python -m unittest
```
