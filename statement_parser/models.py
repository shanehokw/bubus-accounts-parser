from dataclasses import dataclass, field
from datetime import date


@dataclass
class Transaction:
    date: date
    account: str
    value: float  # negative = money out
    description: str
    key: str = ""  # merchant / counterparty, used to learn and match category rules
    category: str = ""
    type: str = ""
    settled: bool = False


@dataclass
class Statement:
    kind: str  # e.g. "Maybank Savings"
    account: str  # value for the ACCOUNT column
    transactions: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    check: str = ""  # human-readable result of the balance check
    check_ok: bool = False

