"""A realistic sample workbook, so the product can be seen before uploading anything.

A new visitor with no spreadsheet to hand sees an upload box and nothing else -
they cannot tell what the app does until they commit their own data to it. This
generates a plausible Indian sales dataset in memory that exercises every part of
the app: measures to total, dimensions to rank, a real timeline, and cities and
states the map can actually place.

It is deterministic, so the numbers a user sees match the numbers in a demo.
"""

import numpy as np
import pandas as pd

CITIES = [
    ("Mumbai", "Maharashtra", "West"), ("Delhi", "Delhi", "North"),
    ("Bangalore", "Karnataka", "South"), ("Hyderabad", "Telangana", "South"),
    ("Chennai", "Tamil Nadu", "South"), ("Kolkata", "West Bengal", "East"),
    ("Pune", "Maharashtra", "West"), ("Ahmedabad", "Gujarat", "West"),
    ("Jaipur", "Rajasthan", "North"), ("Lucknow", "Uttar Pradesh", "North"),
    ("Indore", "Madhya Pradesh", "Central"), ("Kochi", "Kerala", "South"),
    ("Chandigarh", "Chandigarh", "North"), ("Bhopal", "Madhya Pradesh", "Central"),
    ("Patna", "Bihar", "East"), ("Srinagar", "Jammu and Kashmir", "North"),
    ("Guwahati", "Assam", "East"), ("Surat", "Gujarat", "West"),
]

CATEGORIES = {
    "Electronics": ["Laptop", "Monitor", "Keyboard", "Headphones"],
    "Furniture": ["Office Chair", "Desk", "Bookshelf"],
    "Stationery": ["Notebook", "Pen Set", "Printer Paper"],
    "Appliances": ["Microwave", "Air Purifier", "Water Heater"],
}

SALES_REPS = ["Amit Sharma", "Sara Khan", "Rahul Verma", "Priya Nair",
              "Arun Menon", "Neha Gupta"]

CHANNELS = ["Online", "Retail Store", "Distributor", "Direct Sales"]
PAYMENT = ["Paid", "Pending", "Partially Paid"]
STATUS = ["Delivered", "Shipped", "Processing", "Returned"]


def build_sample_workbook(rows=420, seed=11):
    """Return {sheet_name: DataFrame} in the same shape an upload produces."""
    rng = np.random.default_rng(seed)

    city_index = rng.integers(0, len(CITIES), rows)
    cities = [CITIES[i] for i in city_index]

    categories = rng.choice(list(CATEGORIES), rows, p=[0.38, 0.22, 0.25, 0.15])
    products = [CATEGORIES[category][rng.integers(0, len(CATEGORIES[category]))]
                for category in categories]

    # Prices differ by category, so the measures behave like a real catalogue
    # rather than one uniform blur.
    base_price = {"Electronics": 32000, "Furniture": 9500,
                  "Stationery": 450, "Appliances": 14000}
    unit_price = np.array([base_price[c] for c in categories]) * rng.uniform(0.7, 1.4, rows)
    quantity = rng.integers(1, 9, rows)
    discount = np.round(rng.choice([0, 0, 0, 5, 10, 15, 20], rows) / 100, 2)

    gross = unit_price * quantity
    net = gross * (1 - discount)
    tax = net * 0.18

    # A year of orders, weighted so the festive months genuinely stand out.
    start = pd.Timestamp("2025-04-01")
    day_weights = np.ones(365)
    day_weights[180:240] = 2.6          # October-November festive lift
    day_weights /= day_weights.sum()
    offsets = rng.choice(365, rows, p=day_weights)
    order_date = start + pd.to_timedelta(offsets, unit="D")

    sales = pd.DataFrame({
        "Order ID": [f"ORD-{25000 + i}" for i in range(rows)],
        "Order Date": order_date,
        "City": [c[0] for c in cities],
        "State": [c[1] for c in cities],
        "Region": [c[2] for c in cities],
        "Country": "India",
        "Category": categories,
        "Product": products,
        "Sales Rep": rng.choice(SALES_REPS, rows),
        "Channel": rng.choice(CHANNELS, rows, p=[0.42, 0.28, 0.18, 0.12]),
        "Quantity": quantity,
        "Unit Price": np.round(unit_price, 2),
        "Discount": discount,
        "Net Amount": np.round(net, 2),
        "Tax Amount": np.round(tax, 2),
        "Total Amount": np.round(net + tax, 2),
        "Payment Status": rng.choice(PAYMENT, rows, p=[0.72, 0.18, 0.10]),
        "Order Status": rng.choice(STATUS, rows, p=[0.68, 0.17, 0.11, 0.04]),
    })

    return {"Sales 2025-26": sales.sort_values("Order Date").reset_index(drop=True)}
