import requests
import pandas as pd
import streamlit as st

API_BASE = st.secrets.get("API_BASE", "http://127.0.0.1:8000")


@st.cache_data(ttl=5)
def api_get(path: str, params: dict | None = None):
    url = f"{API_BASE}{path}"
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def api_post(path: str, payload: dict):
    url = f"{API_BASE}{path}"
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def api_put(path: str, payload: dict):
    url = f"{API_BASE}{path}"
    r = requests.put(url, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def money_inr(x):
    try:
        return f"₹{float(x):,.2f}"
    except Exception:
        return "—"


st.set_page_config(page_title="Trading Sim Dashboard", layout="wide")

st.title("Trading Simulation Dashboard")
st.caption(f"API: {API_BASE}")

# ---- Sidebar: Strategy Editor + Create Run + Run selection ----
with st.sidebar:
    st.header("Controls")

    # Load symbols + strategies once for the sidebar
    try:
        symbols = api_get("/symbols")
    except Exception as e:
        symbols = []
        st.error(f"Failed to load symbols: {e}")

    try:
        strategies = api_get("/strategies")
    except Exception as e:
        strategies = []
        st.error(f"Failed to load strategies: {e}")

    tickers = [s["ticker"] for s in symbols] if symbols else []
    default_ticker = "RELIANCE" if "RELIANCE" in tickers else (tickers[0] if tickers else "RELIANCE")

    # ===== Strategy Editor =====
    st.subheader("Strategy Editor")

    if strategies:
        strat_labels = [f"{s['name']} ({s['id'][:8]}…)" for s in strategies]
        strat_idx = st.selectbox(
            "Select strategy",
            options=list(range(len(strat_labels))),
            format_func=lambda i: strat_labels[i],
            key="edit_strat_sel",
        )
        selected_strat = strategies[strat_idx]

        edit_name = st.text_input("Name", value=selected_strat["name"], key="edit_strat_name")
        edit_code = st.text_area("Code (Python)", value=selected_strat["code"], height=240, key="edit_strat_code")

        cL, cR = st.columns(2)
        with cL:
            if st.button("Save update", use_container_width=True, key="save_strat_update"):
                try:
                    api_put(f"/strategies/{selected_strat['id']}", {"name": edit_name, "code": edit_code})
                    st.success("Strategy updated")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")

        with cR:
            if st.button("Duplicate as new", use_container_width=True, key="dup_strat"):
                try:
                    created = api_post("/strategies", {"name": f"{edit_name}_copy", "code": edit_code})
                    st.success(f"Created: {created['id']}")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Create failed: {e}")
    else:
        st.info("No strategies yet. Create one below.")

    with st.expander("Create new strategy", expanded=(not strategies)):
        new_name = st.text_input("New strategy name", value="my_strategy", key="new_strat_name")
        new_code = st.text_area(
            "New strategy code",
            value="def init(ctx):\n    pass\n\n\ndef on_bar(ctx, bar):\n    # ctx.buy(bar.symbol, 10)\n    pass\n",
            height=220,
            key="new_strat_code",
        )
        if st.button("Create strategy", use_container_width=True, key="create_strat_btn"):
            try:
                created = api_post("/strategies", {"name": new_name, "code": new_code})
                st.success(f"Created: {created['id']}")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Create failed: {e}")

    st.divider()

    # ===== Create Run =====
    st.subheader("Create run")

    create_ticker = st.selectbox(
        "Symbol",
        options=tickers or [default_ticker],
        index=(tickers.index(default_ticker) if tickers and default_ticker in tickers else 0),
        key="create_symbol",
    )

    if strategies:
        strat_map = {f"{s['name']} ({s['id'][:8]}…)": s["id"] for s in strategies}
        strat_label = st.selectbox("Strategy for run", options=list(strat_map.keys()), key="create_strategy")
        strategy_id = strat_map[strat_label]
    else:
        strategy_id = None
        st.warning("Create a strategy first.")

    # dates: user input
    start_date_ui = st.text_input("Start date (YYYY-MM-DD)", value="2026-02-05", key="create_start")
    end_date_ui = st.text_input("End date (YYYY-MM-DD)", value="2026-02-11", key="create_end")

    starting_cash_inr = st.number_input(
        "Starting cash (₹)",
        min_value=0.0,
        value=1_000_000.0,
        step=10_000.0,
        key="create_cash_inr",
    )
    fee_bps = st.number_input("Fee (bps)", min_value=0, max_value=100, value=1, step=1, key="create_fee")
    slippage_bps = st.number_input("Slippage (bps)", min_value=0, max_value=100, value=2, step=1, key="create_slip")

    # warn if no bars exist for selected range
    try:
        test_bars = api_get(f"/symbols/{create_ticker}/bars", params={"start": start_date_ui, "end": end_date_ui})
        if not test_bars:
            st.warning("No bars found for this symbol/date range. Run may produce empty results.")
    except Exception:
        pass

    if st.button("Run backtest", use_container_width=True, disabled=(strategy_id is None)):
        payload = {
            "strategy_id": strategy_id,
            "symbols": [create_ticker],
            "start_date": start_date_ui,
            "end_date": end_date_ui,
            "starting_cash_paise": int(round(float(starting_cash_inr) * 100)),
            "fee_bps": int(fee_bps),
            "slippage_bps": int(slippage_bps),
        }
        try:
            r = requests.post(f"{API_BASE}/runs", json=payload, timeout=15)
            if r.status_code >= 400:
                st.error(f"Create run failed: {r.status_code} {r.text}")
            else:
                new_run = r.json()
                st.success(f"Queued run: {new_run['id']}")
                st.cache_data.clear()
                st.rerun()
        except Exception as e:
            st.error(f"Create run failed: {e}")

    st.divider()

    # ===== Run selector =====
    runs = api_get("/runs")
    if not runs:
        st.warning("No runs found. Create one above.")
        st.stop()

    run_options = []
    for r in runs:
        rid = r["id"]
        status = r["status"]
        sym = ",".join((r.get("config_json") or {}).get("symbols", []))
        sd = (r.get("config_json") or {}).get("start_date")
        ed = (r.get("config_json") or {}).get("end_date")
        run_options.append((rid, f"{rid[:8]}…  {status}  {sym}  {sd}→{ed}"))

    selected = st.selectbox(
        "Select run",
        options=run_options,
        format_func=lambda x: x[1],
        index=0,
        key="run_selector",
    )
    run_id = selected[0]

    st.divider()

    ticker = st.selectbox(
        "Ticker (price chart)",
        options=tickers or [default_ticker],
        index=(tickers.index(default_ticker) if tickers and default_ticker in tickers else 0),
        key="price_symbol",
    )

    show_equity_overlay = st.checkbox("Overlay equity on price chart (scaled)", value=True, key="overlay")

# ---- Load run details ----
run = api_get(f"/runs/{run_id}")
cfg = run.get("config_json") or {}

start_date = cfg.get("start_date")
end_date = cfg.get("end_date")

colA, colB, colC, colD = st.columns([2, 1, 1, 2])
with colA:
    st.subheader("Run")
    st.write(f"**Run ID:** `{run_id}`")
    st.write(f"**Status:** `{run.get('status')}`")
with colB:
    st.subheader("Range")
    st.write(f"{start_date} → {end_date}")
with colC:
    st.subheader("Symbols")
    st.write(", ".join(cfg.get("symbols", [])) or "—")
with colD:
    st.subheader("Config")
    st.json(
        {
            "starting_cash_paise": cfg.get("starting_cash_paise"),
            "fee_bps": cfg.get("fee_bps"),
            "slippage_bps": cfg.get("slippage_bps"),
            "fill_rule": cfg.get("fill_rule"),
        }
    )

st.divider()

# ---- Fetch series ----
equity = api_get(f"/runs/{run_id}/equity")
fills = api_get(f"/runs/{run_id}/fills")
metrics = api_get(f"/runs/{run_id}/metrics")

eq_df = pd.DataFrame(equity)
if not eq_df.empty:
    eq_df["date"] = pd.to_datetime(eq_df["date"])
    eq_df = eq_df.sort_values("date")

fills_df = pd.DataFrame(fills)
if not fills_df.empty:
    fills_df["date"] = pd.to_datetime(fills_df["date"])
    fills_df = fills_df.sort_values(["date", "order_id"])

bars = api_get(f"/symbols/{ticker}/bars", params={"start": start_date, "end": end_date})
bars_df = pd.DataFrame(bars)
if not bars_df.empty:
    bars_df["date"] = pd.to_datetime(bars_df["date"])
    bars_df = bars_df.sort_values("date")

# ---- Metrics cards ----
st.subheader("Metrics")

m = metrics if isinstance(metrics, dict) else {}
if "metrics" in m and m["metrics"] is not None:
    m = m["metrics"]

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Sharpe", f"{float(m.get('sharpe', 0.0)):.3f}")
c2.metric("Max DD", money_inr(m.get("max_drawdown_inr", 0.0)))
c3.metric("Win rate", f"{(float(m.get('win_rate', 0.0)) * 100):.2f}%")
c4.metric("Trades closed", int(m.get("trades_closed", 0) or 0))
c5.metric("Realized PnL", money_inr(m.get("realized_pnl_inr", 0.0)))
c6.metric("Fees", money_inr(m.get("fees_inr", 0.0)))

st.divider()

# ---- Charts ----
left, right = st.columns([1, 1])

with left:
    st.subheader("Equity curve (₹)")
    if eq_df.empty:
        st.info("No equity points yet.")
    else:
        chart_df = eq_df.set_index("date")[["equity_inr"]]
        st.line_chart(chart_df)

with right:
    st.subheader(f"{ticker} Close (₹)")
    if bars_df.empty:
        st.info("No bars found for ticker/range.")
    else:
        price_df = bars_df.set_index("date")[["close_inr"]].rename(columns={"close_inr": "close"})
        if show_equity_overlay and not eq_df.empty:
            eq_s = eq_df.set_index("date")["equity_inr"]
            pmin, pmax = price_df["close"].min(), price_df["close"].max()
            emin, emax = eq_s.min(), eq_s.max()
            if emax > emin and pmax > pmin:
                eq_scaled = (eq_s - emin) / (emax - emin) * (pmax - pmin) + pmin
                overlay = pd.DataFrame({"close": price_df["close"], "equity_scaled": eq_scaled})
                st.line_chart(overlay)
            else:
                st.line_chart(price_df)
        else:
            st.line_chart(price_df)

st.divider()

# ---- Fills table ----
st.subheader("Fills")
if fills_df.empty:
    st.info("No fills for this run.")
else:
    show = fills_df.copy()
    show["price_inr"] = show["price_inr"].map(lambda x: float(x))
    show["fee_inr"] = show["fee_inr"].map(lambda x: float(x))
    st.dataframe(
        show[["date", "ticker", "side", "qty", "price_inr", "fee_inr", "order_id"]],
        use_container_width=True,
        hide_index=True,
    )
