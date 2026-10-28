from __future__ import annotations

import json
import os
import time
from decimal import Decimal, InvalidOperation

import pandas as pd
import streamlit as st
from openai import APIError, OpenAI

from finance import CATEGORIES, calculate_summary, category_matches_type, parse_transactions
from finance import Transaction


st.set_page_config(page_title="Community Event Fund Tracker", page_icon="🎉", layout="wide")

st.title("Community Event Fund Tracker")
st.caption(
    "Track community donations and event costs. Review every category before using "
    "the totals in your year-end report."
)

with st.sidebar:
    st.header("Fund setup")
    opening_input = st.number_input(
        "2025 opening reserves ($)", min_value=0.0, value=0.0, step=100.0, format="%.2f"
    )
    st.caption("Enter the reserve balance carried into 2026.")
    st.divider()
    st.header("AI categorization")
    api_key = st.text_input(
        "OpenAI API key (optional)",
        value=os.getenv("OPENAI_API_KEY", ""),
        type="password",
        help="Used only when you click the AI categorization button. Your key is not saved.",
    )
    model = st.text_input("Model", value="gpt-4o-mini")
    st.caption(
        "Without an API key, the app still suggests categories using local keyword rules."
    )

uploaded_file = st.file_uploader("Upload transaction CSV", type=["csv"])
st.markdown(
    "Required columns: `date`, `description`, `amount`. Optional columns: `type` "
    "(`income` or `expense`) and `category`. Without `type`, positive amounts are "
    "income and negative amounts are expenses."
)

if not uploaded_file:
    st.info("Upload a CSV to review transactions and build the 2026 fund report.")
    st.code(
        "date,description,amount,type\n"
        "2026-01-15,GoFundMe donation,250.00,income\n"
        "2026-02-02,Tent rental,400.00,expense\n"
        "2026-02-03,Plates and spoons,85.50,expense",
        language="csv",
    )
    st.stop()

try:
    csv_text = uploaded_file.getvalue().decode("utf-8-sig")
    parsed = parse_transactions(csv_text)
except (UnicodeDecodeError, ValueError) as error:
    st.error(f"Could not read this CSV: {error}")
    st.stop()

fingerprint = f"{uploaded_file.name}:{hash(csv_text)}"
if st.session_state.get("upload_fingerprint") != fingerprint:
    st.session_state["upload_fingerprint"] = fingerprint
    st.session_state["transactions"] = [
        {
            "Date": item.date.isoformat(),
            "Description": item.description,
            "Amount": float(item.amount),
            "Type": item.type,
            "Category": item.category,
            "Confidence": "Rule-based",
        }
        for item in parsed
    ]

transactions_df = pd.DataFrame(st.session_state["transactions"])

st.subheader("Review and categorize transactions")
st.caption("Categories are editable. Confirm the AI or rule-based suggestions before reporting.")

if st.button("Suggest categories with AI", type="secondary"):
    if not api_key.strip():
        st.warning("Add an OpenAI API key in the sidebar to use AI categorization.")
    else:
        started = time.perf_counter()
        try:
            response = OpenAI(api_key=api_key.strip()).chat.completions.create(
                model=model.strip() or "gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Categorize community event fund transactions using only the "
                            "provided descriptions and transaction types. Do not alter "
                            "amounts, dates, or types. Use Other expense or Other income "
                            "when the description is unclear. Return one result per input "
                            "item, preserving its integer index. Confidence is from 0 to 1."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            [
                                {
                                    "index": index,
                                    "description": row["Description"],
                                    "type": row["Type"],
                                }
                                for index, row in transactions_df.iterrows()
                            ]
                        ),
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "transaction_categories",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "transactions": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "index": {"type": "integer"},
                                            "category": {
                                                "type": "string",
                                                "enum": list(CATEGORIES),
                                            },
                                            "confidence": {
                                                "type": "number",
                                                "minimum": 0,
                                                "maximum": 1,
                                            },
                                        },
                                        "required": ["index", "category", "confidence"],
                                        "additionalProperties": False,
                                    },
                                }
                            },
                            "required": ["transactions"],
                            "additionalProperties": False,
                        },
                    },
                },
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("The AI returned an empty response.")
            suggestions = json.loads(content)["transactions"]
            if len(suggestions) != len(transactions_df):
                raise ValueError("The AI returned a different number of categories than requested.")
            updated = transactions_df.copy()
            seen = set()
            for suggestion in suggestions:
                index = suggestion["index"]
                category = suggestion["category"]
                confidence = float(suggestion["confidence"])
                if (
                    index < 0
                    or index >= len(updated)
                    or index in seen
                    or category not in CATEGORIES
                    or not 0 <= confidence <= 1
                ):
                    raise ValueError("The AI response contained an invalid category result.")
                seen.add(index)
                if not category_matches_type(category, updated.loc[index, "Type"]):
                    raise ValueError(
                        f"The AI assigned an income/expense category mismatch to "
                        f"'{updated.loc[index, 'Description']}'."
                    )
                updated.loc[index, "Category"] = category
                updated.loc[index, "Confidence"] = f"AI ({confidence:.0%})"
            if len(seen) != len(updated):
                raise ValueError("The AI response did not categorize every transaction.")
            st.session_state["transactions"] = updated.to_dict("records")
            st.session_state["last_ai_latency"] = time.perf_counter() - started
            st.rerun()
        except (APIError, KeyError, ValueError) as error:
            st.error(f"AI categorization failed: {error}")

edited_df = st.data_editor(
    transactions_df,
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    column_config={
        "Date": st.column_config.TextColumn("Date (YYYY-MM-DD)", disabled=True),
        "Description": st.column_config.TextColumn(disabled=True),
        "Amount": st.column_config.NumberColumn(format="$%.2f", disabled=True),
        "Type": st.column_config.SelectboxColumn(options=["income", "expense"], disabled=True),
        "Category": st.column_config.SelectboxColumn(options=list(CATEGORIES), required=True),
        "Confidence": st.column_config.TextColumn(disabled=True),
    },
    key="transaction_editor",
)
st.session_state["transactions"] = edited_df.to_dict("records")

invalid_categories = [
    row["Description"]
    for _, row in edited_df.iterrows()
    if not category_matches_type(row["Category"], row["Type"])
]
if invalid_categories:
    st.error(
        "Each transaction category must match its income or expense type. "
        f"Review: {', '.join(invalid_categories)}."
    )
    st.stop()

try:
    opening_reserve = Decimal(str(opening_input))
    summary = calculate_summary(
        [
            Transaction(
                date=pd.to_datetime(row["Date"]).date(),
                description=row["Description"],
                amount=Decimal(str(row["Amount"])),
                type=row["Type"],
                category=row["Category"],
            )
            for _, row in edited_df.iterrows()
        ],
        opening_reserve,
    )
except (InvalidOperation, ValueError, KeyError) as error:
    st.error(f"Could not calculate the report: {error}")
    st.stop()

st.subheader("2026 fund summary")
metric_columns = st.columns(5)
metric_values = (
    ("2025 opening reserves", summary["opening_reserve"]),
    ("2026 GoFundMe & donations", summary["donations"]),
    ("2026 other income", summary["other_income"]),
    ("2026 expenses", -summary["expenses"]),
    ("Carry forward to 2027", summary["ending_reserve"]),
)
for column, (label, amount) in zip(metric_columns, metric_values):
    column.metric(label, f"${amount:,.2f}")

st.caption(
    "Carry forward = opening reserves + donations + other income − expenses. "
    "Only transactions dated in 2026 are included."
)

year_df = edited_df[pd.to_datetime(edited_df["Date"]).dt.year == 2026].copy()
expense_df = year_df[year_df["Type"] == "expense"]
if expense_df.empty:
    st.info("No 2026 expenses were found to chart.")
else:
    category_totals = (
        expense_df.groupby("Category", as_index=True)["Amount"].sum().sort_values(ascending=False)
    )
    st.subheader("2026 spending by category")
    st.bar_chart(category_totals, horizontal=True)
    st.dataframe(
        category_totals.rename("Total spent").map(lambda value: f"${value:,.2f}"),
        use_container_width=True,
    )

if "last_ai_latency" in st.session_state:
    st.caption(f"Last AI categorization completed in {st.session_state['last_ai_latency']:.2f}s.")

st.download_button(
    "Download reviewed transactions",
    data=edited_df.to_csv(index=False).encode("utf-8"),
    file_name="community_event_transactions_reviewed.csv",
    mime="text/csv",
)
