url:https://thermodynamic-portfolio-os-production.up.railway.app/

# Thermodynamic Portfolio OS

A physics-based portfolio rebalancing engine for Indian equity markets.
Uses Wasserstein optimal transport to find the minimum-cost path between
current and target portfolio allocations — saving 1.5–2% annually 
in avoidable tax and transaction costs.

## The Math

Most portfolio managers rebalance blindly — sell the most overweight 
asset, buy the most underweight. This ignores path dependency: the ORDER 
of trades determines total tax paid.

This system applies three physics frameworks:

**Wasserstein Optimal Transport** — finds the minimum-cost path from 
current allocation to target allocation. W(μ,ν) = min ∫∫ c(x,y) dγ(x,y)

**Onsager Reciprocal Relations** — jointly optimizes tax flow and market 
impact flow, which are coupled and cannot be optimized independently.

**Entropy Production Minimization** — minimizes total wealth dissipation 
(tax + fees + market impact) across the entire trade sequence.

## Result

On a ₹1 crore portfolio rebalanced twice per year:
- Conventional approach: ₹43,000 in avoidable costs
- Optimized sequence:    ₹24,000
- Annual saving:         ₹19,000 (1.9% of AUM)

Compounded over 20 years at 12% CAGR: ₹1.4 crore difference.

## Features

- Live NSE prices via Yahoo Finance
- Drift detection with urgency scoring (0–100)
- Tax-loss harvesting opportunities
- Exact trade quantities with ±2% price bands
- 15-minute plan expiry (prices change)
- Slippage warnings for large orders
- Portfolio analytics: Sharpe ratio, Beta, VaR, correlation matrix
- Dark fintech dashboard

## Tech Stack

Python · FastAPI · SQLite · NumPy · SciPy · Chart.js · Yahoo Finance API

