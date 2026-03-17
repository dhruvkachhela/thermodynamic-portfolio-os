"""
DATABASE — uses only Python's built-in sqlite3
No pip install needed. Works on any Windows machine.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Generator

# Optional SQLAlchemy ORM model for price cache (used by price_fetcher.py)
try:
    from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
    from sqlalchemy.orm import declarative_base, sessionmaker
    SQLALCHEMY_AVAILABLE = True
except Exception:
    SQLALCHEMY_AVAILABLE = False

# DB sits in the same folder as database.py (flat structure)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.db")

# --- SQLAlchemy setup (if available) ---------------------------------
if SQLALCHEMY_AVAILABLE:
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base = declarative_base()

    class PriceCacheDB(Base):
        __tablename__ = "price_cache"
        id = Column(Integer, primary_key=True, index=True)
        symbol = Column(String, unique=True, index=True, nullable=False)
        price = Column(Float, nullable=False, default=0.0)
        last_updated = Column(DateTime, nullable=True)

    class ClientDB(Base):
        __tablename__ = "clients"
        id = Column(String, primary_key=True, index=True)
        name = Column(String, nullable=False)
        email = Column(String, nullable=True)
        phone = Column(String, nullable=True)
        target_allocation = Column(String, nullable=False)  # JSON string
        created_at = Column(DateTime, default=datetime.now)

    class PositionDB(Base):
        __tablename__ = "positions"
        id = Column(Integer, primary_key=True, index=True)
        client_id = Column(String, nullable=False, index=True)
        symbol = Column(String, nullable=False)
        quantity = Column(Float, nullable=False)
        avg_cost = Column(Float, nullable=False)
        asset_class = Column(String, nullable=False)
        purchase_date = Column(String, nullable=False)
        current_price = Column(Float, default=0.0)
        last_updated = Column(DateTime, nullable=True)

    def get_session():
        """Return a new SQLAlchemy session instance. Callers should close it when done."""
        return SessionLocal()

    # Ensure the ORM table exists
    try:
        Base.metadata.create_all(engine)
    except Exception:
        pass

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS clients (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT, phone TEXT,
        target_allocation TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')))""")
    c.execute("""CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id TEXT NOT NULL,
        symbol TEXT NOT NULL, quantity REAL NOT NULL, avg_cost REAL NOT NULL,
        asset_class TEXT NOT NULL, purchase_date TEXT NOT NULL,
        current_price REAL DEFAULT 0, last_updated TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS rebalance_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')), total_savings REAL,
        total_tax REAL, naive_cost REAL, optimized_cost REAL,
        full_plan_json TEXT, executed INTEGER DEFAULT 0)""")
    conn.commit()
    conn.close()
    print("✅ Database ready:", os.path.abspath(DB_PATH))

def seed_demo_data():
    conn = get_connection()
    c = conn.cursor()
    if c.execute("SELECT COUNT(*) FROM clients").fetchone()[0] > 0:
        conn.close()
        print("ℹ️  Demo data already exists")
        return
    clients = [
        ("CLIENT_001","Rajesh Sharma","rajesh@example.com","+91-98765-43210",json.dumps({"equity":60.0,"bond":30.0,"gold":10.0})),
        ("CLIENT_002","Priya Mehta","priya@example.com","+91-87654-32109",json.dumps({"equity":70.0,"bond":20.0,"gold":10.0})),
        ("CLIENT_003","Amit Patel","amit@example.com","+91-76543-21098",json.dumps({"equity":50.0,"bond":40.0,"gold":10.0})),
    ]
    c.executemany("INSERT INTO clients (id,name,email,phone,target_allocation) VALUES (?,?,?,?,?)", clients)
    positions = [
        ("CLIENT_001","RELIANCE.NS",200,2400,"equity","2022-03-15"),
        ("CLIENT_001","TCS.NS",100,3500,"equity","2021-06-10"),
        ("CLIENT_001","HDFCBANK.NS",150,1600,"equity","2024-01-20"),
        ("CLIENT_001","INFY.NS",80,1800,"equity","2023-08-05"),
        ("CLIENT_001","LIQUIDBEES.NS",500,1000,"bond","2022-01-10"),
        ("CLIENT_001","GOLDBEES.NS",400,45,"gold","2021-11-20"),
        ("CLIENT_002","WIPRO.NS",300,450,"equity","2023-02-10"),
        ("CLIENT_002","TATAMOTORS.NS",200,620,"equity","2022-07-15"),
        ("CLIENT_002","LIQUIDBEES.NS",300,1000,"bond","2023-01-05"),
        ("CLIENT_002","GOLDBEES.NS",200,48,"gold","2022-09-20"),
        ("CLIENT_003","BAJFINANCE.NS",50,6000,"equity","2021-04-12"),
        ("CLIENT_003","SBIN.NS",400,550,"equity","2023-11-08"),
        ("CLIENT_003","LIQUIDBEES.NS",800,1000,"bond","2022-06-15"),
        ("CLIENT_003","GOLDBEES.NS",300,42,"gold","2020-12-01"),
    ]
    c.executemany("INSERT INTO positions (client_id,symbol,quantity,avg_cost,asset_class,purchase_date) VALUES (?,?,?,?,?,?)", positions)
    conn.commit()
    conn.close()
    print("✅ Demo data seeded: 3 clients, 14 positions")

def get_all_clients():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM clients").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_client(client_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_positions(client_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM positions WHERE client_id=?", (client_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_price(symbol, price):
    conn = get_connection()
    conn.execute("UPDATE positions SET current_price=?, last_updated=? WHERE symbol=?",
                 (price, datetime.now().isoformat(), symbol))
    conn.commit()
    conn.close()

def save_rebalance_log(client_id, plan_dict):
    conn = get_connection()
    conn.execute("INSERT INTO rebalance_log (client_id,total_savings,total_tax,naive_cost,optimized_cost,full_plan_json) VALUES (?,?,?,?,?,?)",
        (client_id, plan_dict.get("total_savings",0), plan_dict.get("total_tax",0),
         plan_dict.get("total_cost_naive",0), plan_dict.get("total_cost_optimized",0), json.dumps(plan_dict)))
    conn.commit()
    conn.close()

def get_rebalance_history(client_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM rebalance_log WHERE client_id=? ORDER BY created_at DESC LIMIT 20", (client_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_client_db(data):
    conn = get_connection()
    conn.execute("INSERT INTO clients (id,name,email,phone,target_allocation) VALUES (?,?,?,?,?)",
        (data["client_id"],data["name"],data.get("email",""),data.get("phone",""),json.dumps(data["target_allocation"])))
    conn.commit()
    conn.close()

def add_position_db(client_id, data):
    conn = get_connection()
    conn.execute("INSERT INTO positions (client_id,symbol,quantity,avg_cost,asset_class,purchase_date) VALUES (?,?,?,?,?,?)",
        (client_id,data["symbol"],data["quantity"],data["avg_cost"],data["asset_class"],data["purchase_date"]))
    conn.commit()
    conn.close()

def delete_client_db(client_id):
    conn = get_connection()
    conn.execute("DELETE FROM positions WHERE client_id=?", (client_id,))
    conn.execute("DELETE FROM rebalance_log WHERE client_id=?", (client_id,))
    conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
    conn.commit()
    conn.close()