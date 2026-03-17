"""
routes.py — REST API
=====================
ALL imports are flat — no subfolders, no "backend." prefix.

  from database         import init_db, get_client ...
  from portfolio_builder import PortfolioBuilder
  from engines          import DriftDetector, TaxOptimizer, PhysicsEngine
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import json, os, uuid

# ── All imports are flat (same folder) ────────────────────────────────────────

from database import (
    init_db,
    seed_demo_data,
    get_all_clients,
    get_client,
    get_positions,
    update_price,
    save_rebalance_log,
    get_rebalance_history,
    add_client_db,
    add_position_db,
    delete_client_db,
)

from portfolio_builder import PortfolioBuilder

from engines import (
    DriftDetector,
    TaxOptimizer,
    PhysicsEngine,
)

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Thermodynamic Portfolio OS", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request models ─────────────────────────────────────────────────────────────

class NewClientRequest(BaseModel):
    name:          str
    email:         Optional[str] = None
    phone:         Optional[str] = None
    target_equity: float = 60.0
    target_bond:   float = 30.0
    target_gold:   float = 10.0


class NewPositionRequest(BaseModel):
    client_id:     str
    symbol:        str
    display_name:  str
    quantity:      float
    avg_cost:      float
    asset_class:   str
    purchase_date: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Serve the dashboard HTML directly."""
    index = os.path.join(os.path.dirname(__file__), "frontend", "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"status": "running", "docs": "http://localhost:8000/docs"}


@app.get("/api/clients")
def list_clients():
    clients = get_all_clients()
    # Normalize so frontend always gets client_id and client_name
    normalized = []
    for c in clients:
        normalized.append({
            "client_id":   c["id"],
            "client_name": c["name"],
            "email":       c.get("email", ""),
            "phone":       c.get("phone", ""),
        })
    return {"clients": normalized}


@app.get("/api/dashboard")
def get_dashboard():
    clients  = get_all_clients()
    detector = DriftDetector()

    if not clients:
        return {"summary": {"total_clients": 0, "total_aum": 0}, "clients": []}

    portfolios    = []
    drift_reports = []

    for client in clients:
        portfolio = PortfolioBuilder.from_db(client["id"])
        if portfolio:
            portfolios.append(portfolio)
            drift_reports.append(detector.analyze(portfolio))

    total_aum    = sum(p.total_value for p in portfolios)
    urgent_count = sum(1 for r in drift_reports if r.needs_rebalancing)

    clients_out = []
    for report, portfolio in zip(drift_reports, portfolios):
        if report.needs_rebalancing:
            status = "REBALANCE NOW"
        elif report.urgency_score > 30:
            status = "MONITOR"
        else:
            status = "HEALTHY"

        clients_out.append({
            "client_id":       portfolio.client_id,
            "client_name":     portfolio.client_name,
            "portfolio_value": portfolio.total_value,
            "urgency_score":   report.urgency_score,
            "max_drift":       report.max_drift,
            "status":          status,
            "issue":           report.reason,
            "current_alloc":   portfolio.current_allocation,
            "target_alloc":    portfolio.target_allocation,
        })

    clients_out.sort(key=lambda x: x["urgency_score"], reverse=True)

    return {
        "summary": {
            "total_clients":     len(portfolios),
            "urgent_count":      urgent_count,
            "total_aum":         total_aum,
            "potential_savings": total_aum * 0.02,
        },
        "clients": clients_out,
    }


@app.get("/api/portfolio/{client_id}")
def get_portfolio(client_id: str):
    client = get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    portfolio = PortfolioBuilder.from_db(client_id)
    if not portfolio:
        # Client exists but has no positions — return empty state (not 404)
        return {
            "client_id":          client_id,
            "client_name":        client["name"],
            "total_value":        0,
            "current_allocation": {},
            "target_allocation":  {},
            "unrealized_gains":   0,
            "unrealized_losses":  0,
            "positions":          [],
            "no_positions":       True,
            "drift": {"max_drift": 0, "urgency_score": 0, "needs_rebalancing": False, "drifts": {}, "reason": "No positions"},
            "harvest_opportunities": [],
        }

    detector  = DriftDetector()
    optimizer = TaxOptimizer()
    drift     = detector.analyze(portfolio)
    harvest   = optimizer.find_harvest_opportunities(portfolio)

    positions_out = []
    for p in portfolio.positions:
        cost_basis = p.quantity * p.avg_cost
        pct = round((p.unrealized_gain / cost_basis) * 100, 2) if cost_basis > 0 else 0
        positions_out.append({
            "symbol":          p.symbol,
            "display_name":    p.display_name,
            "quantity":        p.quantity,
            "avg_cost":        p.avg_cost,
            "current_price":   p.current_price,
            "current_value":   p.current_value,
            "unrealized_gain": p.unrealized_gain,
            "unrealized_pct":  pct,
            "asset_class":     p.asset_class,
            "is_long_term":    p.is_long_term,
            "tax_rate":        p.tax_rate * 100,
            "purchase_date":   p.purchase_date,
        })

    return {
        "client_id":          portfolio.client_id,
        "client_name":        portfolio.client_name,
        "total_value":        portfolio.total_value,
        "current_allocation": portfolio.current_allocation,
        "target_allocation":  portfolio.target_allocation,
        "unrealized_gains":   portfolio.total_unrealized_gains,
        "unrealized_losses":  portfolio.total_unrealized_losses,
        "positions":          positions_out,
        "drift": {
            "max_drift":         drift.max_drift,
            "urgency_score":     drift.urgency_score,
            "needs_rebalancing": drift.needs_rebalancing,
            "drifts":            drift.drifts,
            "reason":            drift.reason,
        },
        "harvest_opportunities": harvest,
    }


@app.post("/api/portfolio/{client_id}/rebalance")
def generate_rebalancing_plan(client_id: str):
    client = get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    portfolio = PortfolioBuilder.from_db(client_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="No positions found")

    engine = PhysicsEngine()
    plan   = engine.compute_plan(portfolio)

    save_rebalance_log(client_id, {
        "total_savings":        plan.savings,
        "total_tax":            plan.total_tax,
        "total_cost_naive":     plan.cost_naive,
        "total_cost_optimized": plan.cost_optimized,
    })

    return {
        "client_id": client_id,
        "trades": [{
            "step":             t.step,
            "action":           t.action,
            "asset_class":      t.asset_class,
            "symbol":           t.symbol,
            "display_name":     t.display_name,
            "quantity":         t.quantity,
            "live_price":       t.live_price,
            "price_band_low":   t.price_band_low,
            "price_band_high":  t.price_band_high,
            "estimated_value":  t.estimated_value,
            "tax":              t.estimated_tax,
            "market_impact":    t.estimated_impact,
            "fee":              t.estimated_fee,
            "total_cost":       t.total_cost,
            "slippage_warning": t.slippage_warning,
            "slippage_pct":     t.slippage_pct,
            "reason":           t.reason,
        } for t in plan.trades],
        "cost_comparison": {
            "conventional": plan.cost_naive,
            "optimized":    plan.cost_optimized,
            "you_save":     plan.savings,
        },
        "breakdown": {
            "tax":    plan.total_tax,
            "fees":   plan.total_fees,
            "impact": plan.total_impact,
        },
        "physics": {
            "wasserstein_distance": plan.wasserstein_dist,
            "entropy_produced":     plan.entropy_produced,
        },
        "explanation":   plan.explanation,
        "generated_at":  plan.generated_at,
        "expires_at":    plan.expires_at,
        "price_snapshot": plan.price_snapshot,
    }


@app.get("/api/portfolio/{client_id}/harvest")
def get_harvest(client_id: str):
    client = get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    portfolio = PortfolioBuilder.from_db(client_id)
    optimizer = TaxOptimizer()
    return {
        "client_id":     client_id,
        "opportunities": optimizer.find_harvest_opportunities(portfolio),
    }


@app.get("/api/portfolio/{client_id}/history")
def get_history(client_id: str):
    return {"client_id": client_id, "history": get_rebalance_history(client_id)}


@app.post("/api/client")
def add_client(req: NewClientRequest):
    total = req.target_equity + req.target_bond + req.target_gold
    if abs(total - 100.0) > 0.5:
        raise HTTPException(status_code=400, detail=f"Allocations must add to 100%. Got {total}%")

    client_id = f"CLIENT_{uuid.uuid4().hex[:6].upper()}"
    add_client_db({
        "client_id": client_id,
        "name":      req.name,
        "email":     req.email or "",
        "phone":     req.phone or "",
        "target_allocation": {
            "equity": req.target_equity,
            "bond":   req.target_bond,
            "gold":   req.target_gold,
        }
    })
    return {"client_id": client_id, "message": f"Client '{req.name}' created"}


@app.post("/api/position")
def add_position(req: NewPositionRequest):
    client = get_client(req.client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{req.client_id}' not found")

    add_position_db(req.client_id, {
        "symbol":        req.symbol,
        "display_name":  req.display_name,
        "quantity":      req.quantity,
        "avg_cost":      req.avg_cost,
        "asset_class":   req.asset_class,
        "purchase_date": req.purchase_date,
    })
    return {"message": f"Added {req.symbol} to {client['name']}"}


@app.post("/api/prices/refresh")
def refresh_prices():
    from price_fetcher import PriceFetcher
    all_clients = get_all_clients()
    symbols     = set()
    for c in all_clients:
        for p in get_positions(c["id"]):
            symbols.add(p["symbol"])

    if not symbols:
        return {"message": "No symbols found", "refreshed": 0}

    fetcher = PriceFetcher()
    prices  = fetcher.fetch_prices(list(symbols))
    for symbol, price in prices.items():
        update_price(symbol, price)

    return {"refreshed": len(prices), "prices": prices}


@app.delete("/api/client/{client_id}")
def delete_client(client_id: str):
    client = get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")
    delete_client_db(client_id)
    return {"message": f"Client '{client['name']}' deleted successfully"}


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    print("🚀 Starting Thermodynamic Portfolio OS...")

    init_db()
    seed_demo_data()

    # Mount frontend/
    frontend = os.path.join(os.path.dirname(__file__), "frontend")
    if os.path.exists(frontend):
        app.mount("/static", StaticFiles(directory=frontend), name="static")
        print(f"✅ Frontend mounted from {frontend}")
    else:
        print(f"⚠️  No frontend/ folder found at {frontend}")

    print("✅ Ready — open http://localhost:8000")