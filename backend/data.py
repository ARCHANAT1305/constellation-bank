"""Synthetic bank data. Everything here is fake and lives in memory."""
from datetime import datetime, timedelta
import copy

CUSTOMER = {
    "id": "CUST-20481",
    "name": "Aarav Sharma",
    "segment": "Premier",
    "customer_since": "2019-03-14",
    "city": "Chennai",
    "home_country": "IN",
    "kyc_status": "VERIFIED",
    "mobile": "9840012345",
}

# (id, days_ago, hour, minute, merchant, amount, category, channel, city, country, card/account)
_RAW_TXNS = [
    ("T-1001", 1, 3, 12, "GLOBALPAY*LAGOS", 48500, "Online Shopping", "ONLINE", "Lagos", "NG", "CC-1190"),
    ("T-1002", 1, 19, 40, "Swiggy", 642, "Food", "ONLINE", "Chennai", "IN", "CC-1190"),
    ("T-1003", 2, 14, 5, "QuickMart Electronics", 12999, "Electronics", "POS", "Chennai", "IN", "CC-1190"),
    ("T-1004", 2, 14, 7, "QuickMart Electronics", 12999, "Electronics", "POS", "Chennai", "IN", "CC-1190"),
    ("T-1005", 3, 9, 30, "Chennai Metro", 120, "Transport", "POS", "Chennai", "IN", "DC-3377"),
    ("T-1006", 4, 20, 15, "Amazon India", 3499, "Online Shopping", "ONLINE", "Mumbai", "IN", "CC-1190"),
    ("T-1007", 5, 13, 0, "Zomato", 780, "Food", "ONLINE", "Chennai", "IN", "CC-1190"),
    ("T-1008", 6, 8, 45, "Indian Oil", 2500, "Fuel", "POS", "Chennai", "IN", "DC-3377"),
    ("T-1009", 7, 18, 20, "Reliance Fresh", 3180, "Groceries", "POS", "Chennai", "IN", "DC-3377"),
    ("T-1010", 8, 21, 0, "Netflix", 649, "Subscriptions", "ONLINE", "Mumbai", "IN", "CC-1190"),
    ("T-1011", 9, 11, 30, "Apollo Pharmacy", 1240, "Health", "POS", "Chennai", "IN", "DC-3377"),
    ("T-1012", 10, 17, 10, "Myntra", 4599, "Shopping", "ONLINE", "Bengaluru", "IN", "CC-1190"),
    ("T-1013", 11, 12, 15, "Uber", 380, "Transport", "ONLINE", "Chennai", "IN", "CC-1190"),
    ("T-1014", 12, 19, 5, "BigBasket", 2890, "Groceries", "ONLINE", "Chennai", "IN", "CC-1190"),
    ("T-1015", 14, 10, 0, "Rent - S. Iyer", 28000, "Rent", "TRANSFER", "Chennai", "IN", "SB-4821"),
    ("T-1016", 15, 16, 40, "PVR Cinemas", 1100, "Entertainment", "POS", "Chennai", "IN", "CC-1190"),
    ("T-1017", 17, 9, 10, "Airtel Postpaid", 999, "Bills", "ONLINE", "Delhi", "IN", "CC-1190"),
    ("T-1018", 19, 15, 25, "Decathlon", 5400, "Shopping", "POS", "Chennai", "IN", "DC-3377"),
    ("T-1019", 21, 20, 50, "Swiggy", 910, "Food", "ONLINE", "Chennai", "IN", "CC-1190"),
    ("T-1020", 23, 13, 35, "Indian Oil", 2600, "Fuel", "POS", "Chennai", "IN", "DC-3377"),
    ("T-1021", 25, 10, 20, "TNEB Electricity", 2150, "Bills", "ONLINE", "Chennai", "IN", "SB-4821"),
    ("T-1022", 27, 18, 0, "Reliance Fresh", 2760, "Groceries", "POS", "Chennai", "IN", "DC-3377"),
    ("T-1023", 29, 12, 10, "Auto EMI - HDFC", 12450, "Loan EMI", "AUTO_DEBIT", "Chennai", "IN", "SB-4821"),
]


def _ts(days_ago, hour, minute):
    d = datetime.now() - timedelta(days=days_ago)
    return d.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(timespec="minutes")


def _fresh_state():
    return {
        "accounts": [
            {"id": "SB-4821", "type": "Savings", "account_number": "50100234884821", "balance": 184250.75, "currency": "INR"},
            {"id": "CA-7730", "type": "Current", "account_number": "50100234887730", "balance": 62310.20, "currency": "INR"},
        ],
        "cards": [
            {"id": "CC-1190", "type": "Credit", "last4": "1190", "status": "ACTIVE", "limit": 200000, "outstanding": 74857},
            {"id": "DC-3377", "type": "Debit", "last4": "3377", "status": "ACTIVE", "linked_account": "SB-4821"},
        ],
        "beneficiaries": [
            {"name": "Priya Nair", "bank": "ICICI Bank", "account_number": "000401527766"},
            {"name": "Rahul Mehta", "bank": "SBI", "account_number": "31205567890"},
            {"name": "S. Iyer (Landlord)", "bank": "HDFC Bank", "account_number": "50200078123456"},
        ],
        "transactions": [
            {"id": r[0], "ts": _ts(r[1], r[2], r[3]), "merchant": r[4], "amount": r[5], "category": r[6],
             "channel": r[7], "city": r[8], "country": r[9], "source": r[10], "status": "POSTED"}
            for r in _RAW_TXNS
        ],
        "credit": {
            "score": 762, "bureau": "CIBIL (simulated)", "monthly_income": 125000,
            "employment": "Salaried, 6 years", "existing_emi": 12450, "enquiries_6m": 1,
        },
        "loans": [
            {"id": "LN-5521", "type": "Auto", "principal": 650000, "outstanding": 410000, "emi": 12450,
             "rate": 9.2, "months_remaining": 38, "status": "ACTIVE"},
        ],
    }


STATE = _fresh_state()
PENDING = {}  # action_id -> pending sensitive action


def reset():
    global STATE
    STATE.clear()
    STATE.update(copy.deepcopy(_fresh_state()))
    PENDING.clear()
