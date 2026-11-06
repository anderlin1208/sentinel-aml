from datetime import datetime, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.auth import current_user
from app.main import app
from app.models import Profile


def test_end_to_end():
    engine=create_engine('sqlite://', connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session=sessionmaker(engine, expire_on_commit=False)
    admin=Profile(id=str(uuid4()),email='qa@test.local',role='admin')
    def db_override():
        with Session() as db:yield db
    def auth_override():return admin
    app.dependency_overrides[get_db]=db_override
    app.dependency_overrides[current_user]=auth_override
    try:
        with TestClient(app) as client:
            assert client.get('/api/dashboard').status_code==200
            a=client.post('/api/customers',json={'code':'C-1','name':'Cliente Principal'});assert a.status_code==201,a.text
            b=client.post('/api/customers',json={'code':'C-2','name':'Cliente Destino'});assert b.status_code==201,b.text
            src=client.post('/api/accounts',json={'code':'A-1','customer_id':a.json()['id']}).json()
            dst=client.post('/api/accounts',json={'code':'A-2','customer_id':b.json()['id']}).json()
            payload={'external_id':'TX-0001','source_account_id':src['id'],'destination_account_id':dst['id'],'amount':48000,'occurred_at':datetime.now(timezone.utc).isoformat()}
            result=client.post('/api/transactions',json=payload)
            assert result.status_code==201,result.text
            alert=result.json()['alert']
            assert alert and alert['score']>=30
            assert client.post('/api/transactions',json=payload).status_code==409
            case=client.post('/api/cases',json={'alert_id':alert['id'],'title':'Análisis de transacción TX-0001'})
            assert case.status_code==201,case.text
            note=client.post(f'/api/cases/{case.json()["id"]}/notes',json={'body':'Se efectuó revisión de relación transaccional.'})
            assert note.status_code==201
            close=client.patch(f'/api/cases/{case.json()["id"]}',json={'status':'CLOSED_FALSE_POSITIVE','conclusion':'Se verificó documentación y se descartó señal de riesgo.'})
            assert close.status_code==200,close.text
            assert client.get('/api/alerts').json()[0]['status']=='DISMISSED'
            assert client.get('/api/dashboard').json()['transactions']==1
            assert len(client.get('/api/audit').json())>=6
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
