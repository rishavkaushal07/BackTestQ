import csv
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from sqlalchemy import create_engine, text

# ---- config ----
DATABASE_URL = "postgresql+psycopg://rishavkaushal@localhost:5432/trading_sim"
TICKER = "RELIANCE"
CSV_PATH = "data/RELIANCE.csv"

# Your CSV is mm/dd/yyyy (e.g., 02/11/2026)
DATE_FMT = "%m/%d/%Y"
# ----------------


def clean_num(s: str) -> str:
    """
    Input examples:
      '"1,468.55"' -> 1468.55
      '1,560,195' -> 1560195
    """
    if s is None:
        return ""
    s = s.strip().strip('"').strip("'")
    s = s.replace(",", "")
    return s


def rupees_to_paise(x: str) -> int:
    d = Decimal(clean_num(x))
    d = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)


def parse_date_mmddyyyy(x: str) -> str:
    # returns ISO date string YYYY-MM-DD for Postgres DATE insert
    dt = datetime.strptime(x.strip(), DATE_FMT).date()
    return dt.isoformat()


def main():
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    with engine.begin() as conn:
        # ensure uuid function exists
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))

        # ensure symbol exists
        sym_id = conn.execute(
            text("SELECT id FROM symbols WHERE ticker=:t AND is_active=true"),
            {"t": TICKER},
        ).scalar_one_or_none()

        if sym_id is None:
            sym_id = conn.execute(
                text("""
                    INSERT INTO symbols (id, ticker, name, currency, is_active)
                    VALUES (gen_random_uuid(), :t, :name, 'INR', true)
                    RETURNING id
                """),
                {"t": TICKER, "name": TICKER},
            ).scalar_one()

        rows = []
        with open(CSV_PATH, "r", newline="") as f:
            r = csv.DictReader(f)

            # Expect headers exactly like: Date,Open,High,Low,Close,Volume
            for row in r:
                d = parse_date_mmddyyyy(row["Date"])
                o = rupees_to_paise(row["Open"])
                h = rupees_to_paise(row["High"])
                l = rupees_to_paise(row["Low"])
                c = rupees_to_paise(row["Close"])
                v = int(clean_num(row["Volume"]) or "0")

                rows.append(
                    {
                        "symbol_id": sym_id,
                        "date": d,
                        "open_paise": o,
                        "high_paise": h,
                        "low_paise": l,
                        "close_paise": c,
                        "volume": v,
                    }
                )

        if not rows:
            raise RuntimeError(f"No rows parsed from {CSV_PATH}")

        conn.execute(
            text("""
                INSERT INTO bars_daily
                  (symbol_id, date, open_paise, high_paise, low_paise, close_paise, volume)
                VALUES
                  (:symbol_id, :date, :open_paise, :high_paise, :low_paise, :close_paise, :volume)
                ON CONFLICT (symbol_id, date) DO UPDATE SET
                  open_paise  = excluded.open_paise,
                  high_paise  = excluded.high_paise,
                  low_paise   = excluded.low_paise,
                  close_paise = excluded.close_paise,
                  volume      = excluded.volume
            """),
            rows,
        )

        # quick stats
        cnt = conn.execute(
            text("SELECT count(*) FROM bars_daily WHERE symbol_id=:sid"),
            {"sid": sym_id},
        ).scalar_one()

    print(f"Loaded/updated {len(rows)} rows for {TICKER}. Total bars in DB for {TICKER}: {cnt}")


if __name__ == "__main__":
    main()
