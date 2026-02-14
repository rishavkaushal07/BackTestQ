use pyo3::prelude::*;
use std::collections::HashMap;

pub type Money = i64; // paise
pub type Qty = i64;

#[derive(Clone)]
struct Bar {
    date: String, // "YYYY-MM-DD"
    symbol: String,
    open: Money,
    high: Money,
    low: Money,
    close: Money,
    volume: i64,
}

#[derive(Clone)]
struct Fill {
    date: String,
    symbol: String,
    side: String, // "BUY"/"SELL"
    qty: Qty,
    price: Money,
    fee: Money,
    order_id: i64,
}

#[pyclass]
struct Metrics {
    #[pyo3(get)]
    realized_pnl_paise: Money,
    #[pyo3(get)]
    fees_paise: Money,
    #[pyo3(get)]
    trades_closed: i64,
    #[pyo3(get)]
    win_rate: f64,
    #[pyo3(get)]
    max_drawdown_paise: Money,
    #[pyo3(get)]
    max_drawdown_pct: f64,
    #[pyo3(get)]
    sharpe: f64,
    #[pyo3(get)]
    annual_return_pct: f64,
    #[pyo3(get)]
    volatility: f64,
}

#[pyclass]
struct Engine {
    starting_cash: Money,
    cash: Money,
    fee_bps: i64,
    slippage_bps: i64,

    // state
    last_bar_by_symbol: HashMap<String, Bar>,
    pending_orders: Vec<(i64, String, String, Qty)>, // (order_id, symbol, side, qty)
    next_order_id: i64,

    positions: HashMap<String, Qty>,
    avg_cost: HashMap<String, Money>, // avg cost per share in paise, long-only for MVP

    fills: Vec<Fill>,
    equity_curve: Vec<(String, Money)>,

    realized_pnl: Money,
    fees_paid: Money,
    trades_closed: i64,
    wins: i64,

    peak_equity: Money,
    max_dd: Money,
}

fn fee_for(notional: Money, fee_bps: i64) -> Money {
    // fee = notional * bps / 10000 (integer, rounded)
    (notional * fee_bps) / 10_000
}

fn apply_slippage(price: Money, slippage_bps: i64, side: &str) -> Money {
    if slippage_bps == 0 { return price; }
    // BUY worse (higher), SELL worse (lower)
    let bump = (price * slippage_bps) / 10_000;
    match side {
        "BUY" => price + bump,
        "SELL" => price - bump,
        _ => price,
    }
}

#[pymethods]
impl Engine {
    #[new]
    fn new(starting_cash_paise: i64, fee_bps: i64, slippage_bps: i64) -> Self {
        Engine {
            starting_cash: starting_cash_paise,
            cash: starting_cash_paise,
            fee_bps,
            slippage_bps,
            last_bar_by_symbol: HashMap::new(),
            pending_orders: Vec::new(),
            next_order_id: 1,
            positions: HashMap::new(),
            avg_cost: HashMap::new(),
            fills: Vec::new(),
            equity_curve: Vec::new(),
            realized_pnl: 0,
            fees_paid: 0,
            trades_closed: 0,
            wins: 0,
            peak_equity: starting_cash_paise,
            max_dd: 0,
        }
    }

    /// Called once per symbol per day (worker will call in a loop).
    fn on_bar(&mut self, date: String, symbol: String, open_paise: i64, high_paise: i64, low_paise: i64, close_paise: i64, volume: i64) {
        let bar = Bar { date: date.clone(), symbol: symbol.clone(), open: open_paise, high: high_paise, low: low_paise, close: close_paise, volume };
        self.last_bar_by_symbol.insert(symbol, bar);

        // We only append equity point once per date; simplest approach:
        // worker can call engine.end_of_day(date) once per date after all symbols processed.
        // So do nothing here.
    }

    /// Strategy calls this through ctx.buy/sell. Market order only for MVP.
    fn place_market_order(&mut self, symbol: String, side: String, qty: i64) -> i64 {
        let oid = self.next_order_id;
        self.next_order_id += 1;
        self.pending_orders.push((oid, symbol, side, qty));
        oid
    }

    /// Execute fills on NEXT_OPEN using next day's open, so worker should call this at the *start* of day
    /// after loading bars for that date (bars already set via on_bar).
    fn process_fills_for_date(&mut self, date: String) {
        // Fill any orders using today's open for that symbol
        let mut still_pending = Vec::new();

        for (oid, sym, side, qty) in self.pending_orders.drain(..) {
            let bar = match self.last_bar_by_symbol.get(&sym) {
                Some(b) if b.date == date => b.clone(),
                _ => { still_pending.push((oid, sym, side, qty)); continue; }
            };

            let mut px = bar.open;
            px = apply_slippage(px, self.slippage_bps, &side);
            let notional = px.saturating_mul(qty.abs());
            let fee = fee_for(notional, self.fee_bps);

            // Update cash & position (long-only MVP but allow sell to reduce)
            if side == "BUY" {
                let cost = notional + fee;
                self.cash -= cost;
                let old_q = *self.positions.get(&sym).unwrap_or(&0);
                let new_q = old_q + qty;

                // avg cost update (only for long)
                let old_avg = *self.avg_cost.get(&sym).unwrap_or(&0);
                let new_avg = if new_q > 0 {
                    // weighted avg
                    let old_notional = old_avg.saturating_mul(old_q.max(0));
                    let add_notional = px.saturating_mul(qty);
                    (old_notional + add_notional) / new_q
                } else { 0 };
                self.positions.insert(sym.clone(), new_q);
                self.avg_cost.insert(sym.clone(), new_avg);
            } else if side == "SELL" {
                let proceeds = notional - fee;
                self.cash += proceeds;

                let old_q = *self.positions.get(&sym).unwrap_or(&0);
                let sell_qty = qty; // expect positive qty passed for sell
                let new_q = old_q - sell_qty;
                self.positions.insert(sym.clone(), new_q);

                // Realized PnL for long reductions only
                let avg = *self.avg_cost.get(&sym).unwrap_or(&0);
                let pnl = (px - avg).saturating_mul(sell_qty);
                self.realized_pnl += pnl;
                self.trades_closed += 1;
                if pnl > 0 { self.wins += 1; }

                if new_q <= 0 {
                    self.avg_cost.insert(sym.clone(), 0);
                }
            }

            self.fees_paid += fee;

            self.fills.push(Fill {
                date: date.clone(),
                symbol: sym.clone(),
                side: side.clone(),
                qty,
                price: px,
                fee,
                order_id: oid,
            });
        }

        self.pending_orders = still_pending;
    }

    /// Mark end-of-day equity point (cash + sum(pos * close)).
    fn end_of_day(&mut self, date: String) {
        let mut equity = self.cash;
        for (sym, q) in self.positions.iter() {
            if *q == 0 { continue; }
            if let Some(bar) = self.last_bar_by_symbol.get(sym) {
                if bar.date == date {
                    equity += bar.close.saturating_mul(*q);
                }
            }
        }
        self.equity_curve.push((date.clone(), equity));

        // Drawdown tracking
        if equity > self.peak_equity { self.peak_equity = equity; }
        let dd = self.peak_equity - equity;
        if dd > self.max_dd { self.max_dd = dd; }
    }

    fn cash(&self) -> i64 { self.cash }

    fn position(&self, symbol: String) -> i64 {
        *self.positions.get(&symbol).unwrap_or(&0)
    }

    fn equity_curve(&self) -> Vec<(String, i64)> {
        self.equity_curve.clone()
    }

    fn fills(&self) -> Vec<(String, String, String, i64, i64, i64, i64)> {
        // (date, symbol, side, qty, price, fee, order_id)
        self.fills.iter().map(|f| (f.date.clone(), f.symbol.clone(), f.side.clone(), f.qty, f.price, f.fee, f.order_id)).collect()
    }

    fn metrics(&self) -> Metrics {
        let win_rate = if self.trades_closed > 0 {
            (self.wins as f64) / (self.trades_closed as f64)
        } else { 0.0 };

        // Compute daily arithmetic returns, sharpe, annual return and annual volatility.
        let mut sharpe_val: f64 = 0.0;
        let mut annual_return_pct: f64 = 0.0;
        let mut volatility_pct: f64 = 0.0;
        if self.equity_curve.len() >= 2 {
            let mut rets: Vec<f64> = Vec::new();
            for i in 1..self.equity_curve.len() {
                let prev = self.equity_curve[i - 1].1 as f64;
                let cur = self.equity_curve[i].1 as f64;
                if prev == 0.0 { continue; }
                rets.push((cur / prev) - 1.0);
            }
            if !rets.is_empty() {
                let n = rets.len() as f64;
                let mean = rets.iter().sum::<f64>() / n;
                let sd = if rets.len() > 1 {
                    let var = rets.iter().map(|r| (r - mean) * (r - mean)).sum::<f64>() / (n - 1.0);
                    var.sqrt()
                } else {
                    0.0
                };
                if sd != 0.0 {
                    sharpe_val = (mean / sd) * (252f64).sqrt();
                }
                // annualized return (arithmetic) and volatility (std dev annualized) in percent
                annual_return_pct = mean * 252.0 * 100.0;
                volatility_pct = sd * (252f64).sqrt() * 100.0;
            }
        }

        // Compute drawdown percent relative to peak equity
        let dd_pct = if self.peak_equity > 0 {
            (self.max_dd as f64 / self.peak_equity as f64) * 100.0
        } else {
            0.0
        };

        Metrics {
            realized_pnl_paise: self.realized_pnl,
            fees_paise: self.fees_paid,
            trades_closed: self.trades_closed,
            win_rate,
            max_drawdown_paise: self.max_dd,
            max_drawdown_pct: dd_pct,
            sharpe: sharpe_val,
            annual_return_pct,
            volatility: volatility_pct,
        }
    }
}

#[pymodule]
fn trading_engine(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_class::<Engine>()?;
    m.add_class::<Metrics>()?;
    Ok(())
}
