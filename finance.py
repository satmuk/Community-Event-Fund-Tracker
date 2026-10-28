"""CSV parsing, transaction categorization, and deterministic fund calculations."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable


EXPENSE_CATEGORIES = (
    "Food",
    "Tent & equipment rental",
    "Plates & utensils",
    "Truck & transportation",
    "Lighting & electrical",
    "Venue",
    "Decorations",
    "Permits",
    "Other expense",
)
INCOME_CATEGORIES = ("Donations", "Other income")
CATEGORIES = EXPENSE_CATEGORIES + INCOME_CATEGORIES


@dataclass
class Transaction:
    date: date
    description: str
    amount: Decimal
    type: str
    category: str


def _column_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.strip().lower())


def _parse_amount(value: str, row_number: int) -> tuple[Decimal, int]:
    cleaned = value.strip().replace("$", "").replace(",", "")
    is_negative = cleaned.startswith("(") and cleaned.endswith(")")
    if is_negative:
        cleaned = cleaned[1:-1]
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Row {row_number}: amount must be a valid number.") from exc
    if not amount.is_finite():
        raise ValueError(f"Row {row_number}: amount must be finite.")
    return abs(amount), -1 if is_negative or amount < 0 else 1


def _parse_date(value: str, row_number: int) -> date:
    cleaned = value.strip()
    for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(cleaned, date_format).date()
        except ValueError:
            continue
    raise ValueError(
        f"Row {row_number}: date '{cleaned}' must use YYYY-MM-DD or MM/DD/YYYY."
    )


def _transaction_type(value: str, amount_sign: int, row_number: int) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        return "income" if amount_sign > 0 else "expense"
    if cleaned in {"income", "donation", "deposit", "credit", "revenue"}:
        return "income"
    if cleaned in {"expense", "spending", "purchase", "debit", "withdrawal"}:
        return "expense"
    raise ValueError(
        f"Row {row_number}: type must be 'income' or 'expense' (received '{value}')."
    )


def suggest_category(description: str, transaction_type: str) -> str:
    text = description.lower()
    if transaction_type == "income":
        if any(word in text for word in ("gofundme", "donation", "donor", "contribution")):
            return "Donations"
        return "Other income"

    rules = (
        (("food", "cater", "meal", "grocer", "drink", "beverage", "ice"), "Food"),
        (("tent", "canopy", "table", "chair", "equipment rental"), "Tent & equipment rental"),
        (("plate", "spoon", "fork", "utensil", "cup", "napkin", "disposable"), "Plates & utensils"),
        (("truck", "van rental", "transport", "haul", "delivery"), "Truck & transportation"),
        (("light", "electrical", "generator", "extension cord", "power"), "Lighting & electrical"),
        (("venue", "hall rental", "facility"), "Venue"),
        (("decoration", "banner", "flower", "balloon"), "Decorations"),
        (("permit", "license", "inspection"), "Permits"),
    )
    for keywords, category in rules:
        if any(keyword in text for keyword in keywords):
            return category
    return "Other expense"


def category_matches_type(category: str, transaction_type: str) -> bool:
    if transaction_type == "income":
        return category in INCOME_CATEGORIES
    return category in EXPENSE_CATEGORIES


def parse_transactions(csv_text: str) -> list[Transaction]:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise ValueError("The CSV is empty or missing a header row.")

    columns = {_column_name(name): name for name in reader.fieldnames if name}
    aliases = {
        "date": ("date", "transactiondate"),
        "description": ("description", "details", "memo", "item", "name"),
        "amount": ("amount", "total", "value"),
        "type": ("type", "kind", "transactiontype"),
        "category": ("category",),
    }
    selected = {
        key: next((columns[alias] for alias in names if alias in columns), None)
        for key, names in aliases.items()
    }
    missing = [key for key in ("date", "description", "amount") if not selected[key]]
    if missing:
        raise ValueError(
            "CSV must include these columns: date, description, amount. "
            f"Missing: {', '.join(missing)}."
        )

    transactions = []
    for row_number, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        description = (row.get(selected["description"]) or "").strip()
        if not description:
            raise ValueError(f"Row {row_number}: description cannot be empty.")
        amount, sign = _parse_amount(row.get(selected["amount"]) or "", row_number)
        transaction_type = _transaction_type(
            row.get(selected["type"]) or "" if selected["type"] else "",
            sign,
            row_number,
        )
        category = (row.get(selected["category"]) or "").strip() if selected["category"] else ""
        if category and category not in CATEGORIES:
            raise ValueError(f"Row {row_number}: '{category}' is not a supported category.")
        if not category:
            category = suggest_category(description, transaction_type)
        elif not category_matches_type(category, transaction_type):
            raise ValueError(
                f"Row {row_number}: category '{category}' does not match type "
                f"'{transaction_type}'."
            )
        transactions.append(
            Transaction(
                date=_parse_date(row.get(selected["date"]) or "", row_number),
                description=description,
                amount=amount,
                type=transaction_type,
                category=category,
            )
        )
    if not transactions:
        raise ValueError("The CSV contains no transactions.")
    return transactions


def calculate_summary(
    transactions: Iterable[Transaction], opening_reserve: Decimal, year: int = 2026
) -> dict[str, Decimal]:
    donations = Decimal("0")
    other_income = Decimal("0")
    expenses = Decimal("0")
    for transaction in transactions:
        if transaction.date.year != year:
            continue
        if transaction.type == "income":
            if transaction.category == "Donations":
                donations += transaction.amount
            else:
                other_income += transaction.amount
        else:
            expenses += transaction.amount
    return {
        "opening_reserve": opening_reserve,
        "donations": donations,
        "other_income": other_income,
        "expenses": expenses,
        "ending_reserve": opening_reserve + donations + other_income - expenses,
    }
