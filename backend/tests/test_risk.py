from datetime import datetime,timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.models import Customer,Account,Transaction
from app.risk import evaluate

def test_high_amount_flag():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        r=evaluate(db,'a','b',48500,datetime.now(timezone.utc))
        assert r['score'] == 45
        assert {x['code'] for x in r['reasons']} == {'HIGH_AMOUNT','NEW_COUNTERPARTY'}

def test_no_zero_or_negative_risk():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        r=evaluate(db,'a','b',100,datetime.now(timezone.utc))
        assert r['level']=='LOW'
        assert 0<=r['score']<=100
