from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from ..db import get_db
from .. import models, schemas

router = APIRouter(prefix="/portfolios", tags=["portfolios"])

@router.post("", response_model=schemas.PortfolioOut)
def create_portfolio(payload: schemas.PortfolioCreate, db: Session = Depends(get_db)):
    symbols = db.query(models.Symbol).filter(models.Symbol.ticker.in_(payload.tickers)).all()
    if len(symbols) != len(payload.tickers):
        raise HTTPException(400, "One or more tickers not found")

    p = models.Portfolio(name=payload.name)
    db.add(p)
    db.flush()

    for s in symbols:
        db.add(models.PortfolioSymbol(portfolio_id=p.id, symbol_id=s.id))

    db.commit()
    return {"id": p.id, "name": p.name, "tickers": payload.tickers}

@router.get("", response_model=list[schemas.PortfolioOut])
def list_portfolios(db: Session = Depends(get_db)):
    portfolios = db.query(models.Portfolio).all()
    out = []
    for p in portfolios:
        tickers = (
            db.query(models.Symbol.ticker)
            .join(models.PortfolioSymbol, models.Symbol.id == models.PortfolioSymbol.symbol_id)
            .filter(models.PortfolioSymbol.portfolio_id == p.id)
            .all()
        )
        out.append({"id": p.id, "name": p.name, "tickers": [t[0] for t in tickers]})
    return out
