"""
OPTIMIZER ENGINES
==================
Three engines that work on real Portfolio objects:
1. DriftDetector   — is rebalancing needed?
2. TaxOptimizer    — what to sell and in what order
3. PhysicsEngine   — optimal trade sequence using Wasserstein math
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime


# ── DRIFT DETECTOR ────────────────────────────────────────────────────────────

@dataclass
class DriftReport:
    client_id:         str
    client_name:       str
    total_value:       float
    drifts:            Dict[str, float]
    max_drift:         float
    urgency_score:     float
    needs_rebalancing: bool
    reason:            str


class DriftDetector:
    SOFT_THRESHOLD = 3.0
    HARD_THRESHOLD = 5.0

    def analyze(self, portfolio) -> DriftReport:
        current = portfolio.current_allocation
        target  = portfolio.target_allocation
        drifts  = {}

        for ac in set(list(current.keys()) + list(target.keys())):
            drifts[ac] = round(current.get(ac, 0) - target.get(ac, 0), 2)

        max_drift = max(abs(d) for d in drifts.values()) if drifts else 0

        if max_drift <= self.SOFT_THRESHOLD:
            urgency = (max_drift / self.SOFT_THRESHOLD) * 30
        elif max_drift <= self.HARD_THRESHOLD:
            urgency = 30 + ((max_drift - self.SOFT_THRESHOLD) /
                            (self.HARD_THRESHOLD - self.SOFT_THRESHOLD)) * 40
        else:
            urgency = min(70 + (max_drift - self.HARD_THRESHOLD) * 10, 100)

        worst = max(drifts, key=lambda k: abs(drifts[k])) if drifts else "N/A"
        direction = "overweight" if drifts.get(worst, 0) > 0 else "underweight"
        reason = (f"{worst.capitalize()} is {direction} by {abs(drifts.get(worst,0)):.1f}% "
                  f"(currently {current.get(worst,0):.1f}%, "
                  f"target {target.get(worst,0):.1f}%)")

        return DriftReport(
            client_id         = portfolio.client_id,
            client_name       = portfolio.client_name,
            total_value       = portfolio.total_value,
            drifts            = drifts,
            max_drift         = round(max_drift, 2),
            urgency_score     = round(urgency, 1),
            needs_rebalancing = max_drift >= self.HARD_THRESHOLD,
            reason            = reason,
        )

    def scan_all(self, portfolios) -> List[DriftReport]:
        reports = [self.analyze(p) for p in portfolios]
        reports.sort(key=lambda r: r.urgency_score, reverse=True)
        return reports


# ── TAX OPTIMIZER ─────────────────────────────────────────────────────────────

@dataclass
class SellRecommendation:
    symbol:          str
    display_name:    str
    quantity:        float
    value_raised:    float
    tax_cost:        float
    gain_or_loss:    float
    reason:          str


@dataclass
class TaxOptimizationResult:
    target_amount:        float
    recommendations:      List[SellRecommendation]
    total_tax_naive:      float
    total_tax_optimized:  float
    tax_saved:            float
    losses_harvested:     float


class TaxOptimizer:

    def optimize(self, portfolio, asset_class: str, amount: float) -> TaxOptimizationResult:
        positions = portfolio.get_positions_by_class(asset_class)
        if not positions:
            return TaxOptimizationResult(amount, [], 0, 0, 0, 0)

        naive_tax = self._naive_tax(positions, amount)

        losses   = sorted([p for p in positions if p.unrealized_gain < 0],
                           key=lambda p: p.current_value)
        lt_gains = sorted([p for p in positions if p.unrealized_gain >= 0 and p.is_long_term],
                           key=lambda p: p.current_value)
        st_gains = sorted([p for p in positions if p.unrealized_gain >= 0 and not p.is_long_term],
                           key=lambda p: p.current_value)

        ordered = losses + lt_gains + st_gains
        recs, remaining, total_tax, losses_harvested = [], amount, 0.0, 0.0

        for pos in ordered:
            if remaining <= 0:
                break
            qty = pos.quantity if pos.current_value <= remaining else (remaining / pos.current_value) * pos.quantity
            val = min(pos.current_value, remaining)
            gain = qty * (pos.current_price - pos.avg_cost)
            tax  = max(0, gain * pos.tax_rate)

            if gain < 0:
                losses_harvested += abs(gain)
                reason = f"Loss harvest — saves ~₹{abs(gain)*0.20:,.0f} in tax"
            elif pos.is_long_term:
                reason = f"Long-term gain — 12.5% tax rate"
            else:
                reason = f"Short-term gain — 20% tax (last resort)"

            recs.append(SellRecommendation(
                symbol       = pos.symbol,
                display_name = pos.display_name,
                quantity     = round(qty, 2),
                value_raised = round(val, 0),
                tax_cost     = round(tax, 0),
                gain_or_loss = round(gain, 0),
                reason       = reason,
            ))
            total_tax += tax
            remaining -= val

        return TaxOptimizationResult(
            target_amount       = amount,
            recommendations     = recs,
            total_tax_naive     = round(naive_tax, 0),
            total_tax_optimized = round(total_tax, 0),
            tax_saved           = round(naive_tax - total_tax, 0),
            losses_harvested    = round(losses_harvested, 0),
        )

    def _naive_tax(self, positions, amount):
        total, remaining = 0.0, amount
        for pos in sorted(positions, key=lambda p: p.current_value, reverse=True):
            if remaining <= 0:
                break
            frac  = min(1.0, remaining / pos.current_value)
            gain  = pos.quantity * frac * (pos.current_price - pos.avg_cost)
            total += max(0, gain * pos.tax_rate)
            remaining -= pos.current_value * frac
        return total

    def find_harvest_opportunities(self, portfolio) -> List[dict]:
        opps = []
        for pos in portfolio.positions:
            if pos.unrealized_gain < -50000:
                saving = abs(pos.unrealized_gain) * 0.20
                opps.append({
                    "symbol":        pos.symbol,
                    "display_name":  pos.display_name,
                    "loss_amount":   round(abs(pos.unrealized_gain), 0),
                    "tax_saving":    round(saving, 0),
                    "action":        f"Sell {pos.quantity} units of {pos.display_name}",
                    "urgency":       "HIGH" if abs(pos.unrealized_gain) > 500000 else "MEDIUM",
                })
        opps.sort(key=lambda x: x["tax_saving"], reverse=True)
        return opps


# ── PHYSICS ENGINE ────────────────────────────────────────────────────────────

@dataclass
class TradeInstruction:
    step:                   int
    action:                 str     # BUY or SELL
    asset_class:            str
    symbol:                 str
    display_name:           str
    quantity:               float   # exact units to trade
    live_price:             float = 0.0   # price at plan generation time
    price_band_low:         float = 0.0   # cancel if price drops below this
    price_band_high:        float = 0.0   # cancel if price rises above this
    estimated_value:        float = 0.0
    estimated_tax:          float = 0.0
    estimated_impact:       float = 0.0
    estimated_fee:          float = 0.0
    total_cost:             float = 0.0
    slippage_warning:       bool  = False  # True if large order vs daily volume
    slippage_pct:           float = 0.0    # estimated slippage %
    reason:                 str   = ""


@dataclass
class RebalancingPlan:
    client_id:          str
    trades:             List[TradeInstruction]
    cost_optimized:     float
    cost_naive:         float
    savings:            float
    total_tax:          float
    total_fees:         float
    total_impact:       float
    wasserstein_dist:   float
    entropy_produced:   float
    explanation:        str
    generated_at:       str = ""       # ISO timestamp when plan was made
    expires_at:         str = ""       # Plan expires after 15 min (prices stale)
    price_snapshot:     dict = field(default_factory=dict)  # prices used in plan


class PhysicsEngine:
    FEE_RATE        = 0.001   # 0.1% brokerage
    IMPACT_COEFF    = 0.10
    AVG_DAILY_VOL   = 50_000_000

    def compute_plan(self, portfolio) -> RebalancingPlan:
        current = portfolio.current_allocation
        target  = portfolio.target_allocation
        total   = portfolio.total_value

        # What needs to change (in ₹)
        trades_needed = {}
        for ac in set(list(current.keys()) + list(target.keys())):
            diff = ((target.get(ac, 0) - current.get(ac, 0)) / 100) * total
            if abs(diff) > 1000:
                trades_needed[ac] = diff   # positive = BUY, negative = SELL

        if not trades_needed:
            return RebalancingPlan(portfolio.client_id, [], 0, 0, 0, 0, 0, 0, 0, 0,
                                   "Portfolio is already optimally balanced.")

        cost_matrix  = self._build_cost_matrix(portfolio, trades_needed)
        sequence     = self._wasserstein_sequence(trades_needed, cost_matrix)
        trades       = self._build_trades(sequence, portfolio, trades_needed, cost_matrix)

        total_tax    = sum(t.estimated_tax    for t in trades)
        total_fees   = sum(t.estimated_fee    for t in trades)
        total_impact = sum(t.estimated_impact for t in trades)
        cost_opt     = sum(t.total_cost       for t in trades)
        cost_naive   = self._naive_cost(portfolio, trades_needed)
        savings      = cost_naive - cost_opt
        w_dist       = self._wasserstein_distance(current, target, total)
        entropy      = cost_opt / total if total else 0

        explanation = (
            f"Optimal plan: {sum(1 for t in trades if t.action=='SELL')} sell(s) "
            f"then {sum(1 for t in trades if t.action=='BUY')} buy(s). "
            f"Sells first to pre-fund buys and harvest losses. "
            f"Saves ₹{savings:,.0f} vs conventional rebalancing."
        )

        from datetime import timedelta
        now        = datetime.now()
        expires    = now + timedelta(minutes=15)
        price_snap = {t.symbol: t.live_price for t in trades}

        return RebalancingPlan(
            client_id        = portfolio.client_id,
            trades           = trades,
            cost_optimized   = round(cost_opt, 0),
            cost_naive       = round(cost_naive, 0),
            savings          = round(savings, 0),
            total_tax        = round(total_tax, 0),
            total_fees       = round(total_fees, 0),
            total_impact     = round(total_impact, 0),
            wasserstein_dist = round(w_dist, 4),
            entropy_produced = round(entropy, 6),
            explanation      = explanation,
            generated_at     = now.strftime("%Y-%m-%dT%H:%M:%S"),
            expires_at       = expires.strftime("%Y-%m-%dT%H:%M:%S"),
            price_snapshot   = price_snap,
        )

    def _build_cost_matrix(self, portfolio, trades_needed):
        matrix = {}
        for ac, val in trades_needed.items():
            abs_val = abs(val)
            fee     = abs_val * self.FEE_RATE
            impact  = self.IMPACT_COEFF * np.sqrt(abs_val / self.AVG_DAILY_VOL) * abs_val
            tax     = 0.0
            if val < 0:  # it's a SELL
                positions  = portfolio.get_positions_by_class(ac)
                total_val  = sum(p.current_value for p in positions) or 1
                gains      = sum(max(0, p.unrealized_gain) for p in positions)
                frac       = abs_val / total_val
                tax        = gains * frac * 0.15   # blended rate
            matrix[ac] = {
                "trade_value": val,
                "fee":   round(fee, 0),
                "impact":round(impact, 0),
                "tax":   round(tax, 0),
                "total": round(fee + impact + tax, 0),
            }
        return matrix

    def _wasserstein_sequence(self, trades_needed, cost_matrix):
        sells = sorted([ac for ac in trades_needed if trades_needed[ac] < 0],
                        key=lambda ac: cost_matrix[ac]["tax"])  # cheapest tax first
        buys  = sorted([ac for ac in trades_needed if trades_needed[ac] > 0],
                        key=lambda ac: abs(trades_needed[ac]), reverse=True)
        return sells + buys

    # Average daily volume estimates for NSE stocks (in ₹)
    DAILY_VOLUMES = {
        "equity":  500_000_000,   # ₹50 Cr avg
        "bond":    200_000_000,
        "gold":    100_000_000,
    }
    SLIPPAGE_THRESHOLD = 0.005   # warn if order > 0.5% of daily volume
    PRICE_BAND_PCT     = 0.02    # ±2% price band — cancel if price moves beyond this

    def _build_trades(self, sequence, portfolio, trades_needed, cost_matrix):
        trades = []
        for step, ac in enumerate(sequence, 1):
            val    = trades_needed[ac]
            costs  = cost_matrix[ac]
            action = "SELL" if val < 0 else "BUY"
            pos    = portfolio.get_positions_by_class(ac)
            symbol = pos[0].symbol        if pos else ac.upper()
            dname  = pos[0].display_name  if pos else ac.upper()
            price  = pos[0].current_price if pos else 100

            # Exact integer units (can't buy 0.3 of a stock)
            qty_raw = abs(val) / price
            qty     = int(qty_raw)  # floor to whole units
            if qty == 0:
                qty = 1
            actual_value = qty * price   # recalculate with rounded qty

            # Price band — plan is invalid if price moves >2% from now
            band_low  = round(price * (1 - self.PRICE_BAND_PCT), 2)
            band_high = round(price * (1 + self.PRICE_BAND_PCT), 2)

            # Slippage warning — large order vs daily volume
            daily_vol       = self.DAILY_VOLUMES.get(ac, 500_000_000)
            order_pct       = actual_value / daily_vol
            slippage_warn   = order_pct > self.SLIPPAGE_THRESHOLD
            slippage_pct    = round(order_pct * 10, 3)  # rough estimate

            reason = (
                f"Reduce {ac} by {abs(val/portfolio.total_value*100):.1f}% — "
                f"sell {qty} units @ ₹{price:,.1f}. "
                f"Tax-optimized: losses harvested first."
                if action == "SELL" else
                f"Increase {ac} by {abs(val/portfolio.total_value*100):.1f}% — "
                f"buy {qty} units @ ₹{price:,.1f}. "
                f"Funded by prior sells."
            )

            trades.append(TradeInstruction(
                step             = step,
                action           = action,
                asset_class      = ac,
                symbol           = symbol,
                display_name     = dname,
                quantity         = qty,
                live_price       = round(price, 2),
                price_band_low   = band_low,
                price_band_high  = band_high,
                estimated_value  = round(actual_value, 0),
                estimated_tax    = costs["tax"],
                estimated_impact = costs["impact"],
                estimated_fee    = costs["fee"],
                total_cost       = costs["total"],
                slippage_warning = slippage_warn,
                slippage_pct     = slippage_pct,
                reason           = reason,
            ))
        return trades

    def _naive_cost(self, portfolio, trades_needed):
        total = 0
        for ac, val in trades_needed.items():
            abs_val = abs(val)
            fee     = abs_val * self.FEE_RATE
            impact  = self.IMPACT_COEFF * np.sqrt(abs_val / self.AVG_DAILY_VOL) * abs_val * 1.5
            tax     = 0
            if val < 0:
                positions = portfolio.get_positions_by_class(ac)
                total_val = sum(p.current_value for p in positions) or 1
                gains     = sum(max(0, p.unrealized_gain) for p in positions)
                tax       = gains * (abs_val / total_val) * 0.20
            total += fee + impact + tax
        return round(total, 0)

    def _wasserstein_distance(self, current, target, total):
        all_ac = set(list(current.keys()) + list(target.keys()))
        disp = sum(abs(current.get(ac,0)/100 * total - target.get(ac,0)/100 * total)
                   for ac in all_ac)
        return disp / total if total else 0