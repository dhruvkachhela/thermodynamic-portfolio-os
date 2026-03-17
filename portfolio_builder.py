"""
PORTFOLIO BUILDER
=================
Loads data from database.py, fetches live prices,
builds Portfolio objects for the engines.

All files in same folder — imports are just:
  from database import get_client, get_positions
  from price_fetcher import PriceFetcher
"""

import json
from datetime import datetime
from typing import List, Optional

# Flat imports — same folder
from database import get_client, get_positions, get_all_clients
from price_fetcher import PriceFetcher


class Position:
    def __init__(self, symbol, display_name, quantity, avg_cost,
                 current_price, asset_class, purchase_date):
        self.symbol        = symbol
        self.display_name  = display_name
        self.quantity      = quantity
        self.avg_cost      = avg_cost
        self.current_price = current_price
        self.asset_class   = asset_class
        self.purchase_date = purchase_date

    @property
    def current_value(self):
        return self.quantity * self.current_price

    @property
    def unrealized_gain(self):
        return self.current_value - (self.quantity * self.avg_cost)

    @property
    def is_long_term(self):
        purchase = datetime.strptime(self.purchase_date, "%Y-%m-%d")
        return (datetime.now() - purchase).days > 365

    @property
    def tax_rate(self):
        return 0.125 if self.is_long_term else 0.20

    @property
    def tax_if_sold(self):
        return max(0, self.unrealized_gain * self.tax_rate)


class Portfolio:
    def __init__(self, client_id, client_name, positions, target_allocation):
        self.client_id         = client_id
        self.client_name       = client_name
        self.positions         = positions
        self.target_allocation = target_allocation

    @property
    def total_value(self):
        return sum(p.current_value for p in self.positions)

    @property
    def current_allocation(self):
        if self.total_value == 0:
            return {}
        alloc = {}
        for p in self.positions:
            alloc[p.asset_class] = alloc.get(p.asset_class, 0) + p.current_value
        return {k: round((v / self.total_value) * 100, 2) for k, v in alloc.items()}

    @property
    def total_unrealized_gains(self):
        return sum(p.unrealized_gain for p in self.positions if p.unrealized_gain > 0)

    def get_positions_by_class(self, asset_class):
        return [p for p in self.positions if p.asset_class == asset_class]

    @property
    def total_unrealized_losses(self):
        return sum(p.unrealized_gain for p in self.positions if p.unrealized_gain < 0)


class PortfolioBuilder:

    @staticmethod
    def from_db(client_id: str) -> Optional[Portfolio]:
        # Load from database.py
        client       = get_client(client_id)
        if not client:
            return None

        db_positions = get_positions(client_id)
        if not db_positions:
            return None

        # Fetch live prices
        symbols     = list(set(p["symbol"] for p in db_positions))
        fetcher     = PriceFetcher()
        live_prices = fetcher.fetch_prices(symbols)

        # Build Position objects
        positions = []
        for p in db_positions:
            symbol = p["symbol"]
            price  = live_prices.get(symbol, p.get("current_price") or p["avg_cost"])
            positions.append(Position(
                symbol        = symbol,
                display_name  = p.get("display_name") or symbol,
                quantity      = p["quantity"],
                avg_cost      = p["avg_cost"],
                current_price = price,
                asset_class   = p["asset_class"],
                purchase_date = p["purchase_date"],
            ))

        # Parse target allocation JSON
        raw = client.get("target_allocation") or "{}"
        target = json.loads(raw) if isinstance(raw, str) else raw

        return Portfolio(
            client_id         = client["id"],
            client_name       = client["name"],
            positions         = positions,
            target_allocation = target,
        )

    @staticmethod
    def from_db_all() -> List[Portfolio]:
        clients    = get_all_clients()
        portfolios = []
        for c in clients:
            p = PortfolioBuilder.from_db(c["id"])
            if p:
                portfolios.append(p)
        return portfolios