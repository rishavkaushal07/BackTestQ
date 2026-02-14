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

@router.get("/{portfolio_id}", response_model=schemas.PortfolioOut)
def get_portfolio(portfolio_id: UUID, db: Session = Depends(get_db)):
    p = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    tickers = (
        db.query(models.Symbol.ticker)
        .join(models.PortfolioSymbol, models.Symbol.id == models.PortfolioSymbol.symbol_id)
        .filter(models.PortfolioSymbol.portfolio_id == portfolio_id)
        .all()
    )

    return {
        "id": p.id,
        "name": p.name,
        "tickers": [t[0] for t in tickers],
    }


@router.put("/{portfolio_id}", response_model=schemas.PortfolioOut)
def update_portfolio(portfolio_id: UUID, payload: schemas.UpdatePortfolioRequest, db: Session = Depends(get_db)):
    p = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    if payload.name is not None:
        p.name = payload.name

    if payload.tickers is not None:
        # Validate tickers exist
        symbols = db.query(models.Symbol).filter(models.Symbol.ticker.in_(payload.tickers)).all()
        if len(symbols) != len(payload.tickers):
            raise HTTPException(400, "One or more tickers not found")
        # Delete existing mappings and insert new ones
        db.query(models.PortfolioSymbol).filter(models.PortfolioSymbol.portfolio_id == portfolio_id).delete()
        for s in symbols:
            db.add(models.PortfolioSymbol(portfolio_id=p.id, symbol_id=s.id))

    db.add(p)
    db.commit()
    # return current tickers
    tickers = (
        db.query(models.Symbol.ticker)
        .join(models.PortfolioSymbol, models.Symbol.id == models.PortfolioSymbol.symbol_id)
        .filter(models.PortfolioSymbol.portfolio_id == portfolio_id)
        .all()
    )
    return {"id": p.id, "name": p.name, "tickers": [t[0] for t in tickers]}


@router.delete("/{portfolio_id}")
def delete_portfolio(portfolio_id: UUID, db: Session = Depends(get_db)):
    p = db.query(models.Portfolio).filter(models.Portfolio.id == portfolio_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    # delete cascades via relationship
    db.delete(p)
    db.commit()
    return {"ok": True}
