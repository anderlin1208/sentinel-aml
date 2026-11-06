from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from pydantic import BaseModel, Field, ConfigDict
import csv, io, uuid
from contextlib import asynccontextmanager
from .db import get_db, engine, Base
from .config import settings
from .models import Profile, Customer, Account, Transaction, Alert, Case, CaseNote, AuditLog
from .auth import current_user, require_role
from .risk import evaluate, RULES

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings().env == 'production' and settings().database_url.startswith('sqlite'):
        raise RuntimeError('DATABASE_URL PostgreSQL es obligatorio en producción')
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title='Sentinel AML API', version='1.0.0', docs_url='/api/docs', openapi_url='/api/openapi.json', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[s.strip() for s in settings().cors_origins.split(',') if s.strip()], allow_credentials=True, allow_methods=['GET','POST','PATCH'], allow_headers=['Authorization','Content-Type'])

class CustomerIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=180)
    segment: str = Field(default='PERSONA', max_length=30)
    region: str = Field(default='PERU', max_length=80)

class AccountIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    customer_id: str
    currency: Literal['PEN','USD'] = 'PEN'

class TxIn(BaseModel):
    external_id: str = Field(min_length=2, max_length=100)
    source_account_id: str
    destination_account_id: str
    amount: float = Field(gt=0, le=100000000)
    currency: Literal['PEN'] = 'PEN'
    channel: Literal['TRANSFER','MOBILE','AGENCY','WEB','ATM'] = 'TRANSFER'
    occurred_at: datetime
    synthetic: bool = False

class CaseIn(BaseModel):
    alert_id: str
    title: str = Field(min_length=4,max_length=180)

class CaseUpdate(BaseModel):
    status: Literal['OPEN','IN_REVIEW','ESCALATED','CLOSED_FALSE_POSITIVE','CLOSED_CONFIRMED']
    conclusion: str | None = Field(default=None, max_length=4000)

class NoteIn(BaseModel):
    body: str = Field(min_length=3,max_length=4000)

class AlertUpdate(BaseModel):
    status: Literal['OPEN','INVESTIGATING','DISMISSED','RESOLVED']

class RoleUpdate(BaseModel):
    role: Literal['admin','supervisor','analyst','viewer','pending']

def log(db, user, action, typ, ident, details=None):
    db.add(AuditLog(actor_id=user.id, action=action, entity_type=typ, entity_id=ident, details=details or {}))

def serialize(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

def get_or_404(db, cls, id):
    found = db.get(cls, id)
    if not found: raise HTTPException(404, 'Registro no encontrado')
    return found

@app.get('/api/health')
def health(): return {'status':'ok','service':'sentinel-aml'}

@app.get('/api/me')
def me(user: Profile = Depends(current_user)): return serialize(user)

@app.get('/api/dashboard')
def dashboard(db: Session=Depends(get_db), user: Profile=Depends(current_user)):
    total = db.scalar(select(func.count()).select_from(Transaction)) or 0
    alerts = db.scalar(select(func.count()).select_from(Alert)) or 0
    open_alerts = db.scalar(select(func.count()).select_from(Alert).where(Alert.status.in_(['OPEN','INVESTIGATING']))) or 0
    cases = db.scalar(select(func.count()).select_from(Case).where(~Case.status.like('CLOSED%'))) or 0
    volume = db.scalar(select(func.sum(Transaction.amount))) or 0
    levels = {level: db.scalar(select(func.count()).select_from(Transaction).where(Transaction.risk_level == level)) or 0 for level in ['LOW','MEDIUM','HIGH','CRITICAL']}
    recent = db.scalars(select(Transaction).order_by(Transaction.occurred_at.desc()).limit(8)).all()
    last_alerts = db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(6)).all()
    return {'transactions':total, 'alerts':alerts,'open_alerts':open_alerts,'open_cases':cases,'volume':volume,'levels':levels,'recent_transactions':[serialize(x) for x in recent], 'recent_alerts':[serialize(x) for x in last_alerts]}

@app.get('/api/rules')
def rules(user: Profile=Depends(current_user)): return RULES

@app.get('/api/customers')
def customers(db: Session=Depends(get_db), user: Profile=Depends(current_user)):
    return [serialize(x) for x in db.scalars(select(Customer).order_by(Customer.name).limit(500)).all()]

@app.post('/api/customers',status_code=201)
def create_customer(data:CustomerIn, db:Session=Depends(get_db),user:Profile=Depends(require_role('admin','analyst','supervisor'))):
    if db.scalar(select(Customer.id).where(Customer.code == data.code)): raise HTTPException(409,'Código de cliente duplicado')
    x=Customer(**data.model_dump());db.add(x);db.flush();log(db,user,'CREATE','customer',x.id);db.commit();return serialize(x)

@app.get('/api/accounts')
def accounts(db: Session=Depends(get_db),user:Profile=Depends(current_user)):
    return [serialize(x) for x in db.scalars(select(Account).order_by(Account.code).limit(1000)).all()]

@app.post('/api/accounts',status_code=201)
def create_account(data:AccountIn,db:Session=Depends(get_db),user:Profile=Depends(require_role('admin','analyst','supervisor'))):
    get_or_404(db,Customer,data.customer_id)
    if db.scalar(select(Account.id).where(Account.code==data.code)):raise HTTPException(409,'Código de cuenta duplicado')
    x=Account(**data.model_dump());db.add(x);db.flush();log(db,user,'CREATE','account',x.id);db.commit();return serialize(x)

def insert_tx(db:Session, payload:TxIn, user:Profile):
    if payload.source_account_id == payload.destination_account_id: raise HTTPException(422,'Las cuentas deben ser diferentes')
    if payload.occurred_at > datetime.now(timezone.utc)+timedelta(minutes=5): raise HTTPException(422,'Fecha futura no permitida')
    if payload.occurred_at.tzinfo is None: raise HTTPException(422,'La fecha debe incluir zona horaria')
    if db.scalar(select(Transaction.id).where(Transaction.external_id==payload.external_id)):
        raise HTTPException(409,'Identificador de transacción duplicado')
    source=get_or_404(db,Account,payload.source_account_id);target=get_or_404(db,Account,payload.destination_account_id)
    if source.status!='ACTIVE' or target.status!='ACTIVE' or source.currency!='PEN' or target.currency!='PEN':raise HTTPException(422,'Cuentas incompatibles o inactivas')
    outcome=evaluate(db,payload.source_account_id,payload.destination_account_id,payload.amount,payload.occurred_at)
    tx=Transaction(**payload.model_dump(),risk_score=outcome['score'],risk_level=outcome['level'],flags=outcome['reasons'])
    db.add(tx);db.flush()
    alert=None
    if outcome['score'] >= 30:
        alert=Alert(transaction_id=tx.id,severity=outcome['level'],score=outcome['score'],reasons=outcome['reasons'])
        db.add(alert);db.flush()
    log(db,user,'EVALUATE','transaction',tx.id,{'score':outcome['score'],'alert_id':alert.id if alert else None})
    return {'transaction':serialize(tx),'alert':serialize(alert) if alert else None}

@app.post('/api/transactions',status_code=201)
def create_transaction(data:TxIn,db:Session=Depends(get_db),user:Profile=Depends(require_role('admin','analyst','supervisor'))):
    result=insert_tx(db,data,user);db.commit();return result

@app.get('/api/transactions')
def transactions(limit:int=Query(50,ge=1,le=200), offset:int=Query(0,ge=0),risk:str|None=None,db:Session=Depends(get_db),user:Profile=Depends(current_user)):
    query=select(Transaction)
    if risk: query=query.where(Transaction.risk_level==risk.upper())
    return [serialize(x) for x in db.scalars(query.order_by(Transaction.occurred_at.desc()).offset(offset).limit(limit)).all()]

@app.post('/api/transactions/import')
async def import_csv(file:UploadFile=File(...),db:Session=Depends(get_db),user:Profile=Depends(require_role('admin','supervisor'))):
    content=await file.read(1024*1024+1)
    if len(content)>1024*1024:raise HTTPException(413,'Máximo 1 MB por archivo')
    try: rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    except (UnicodeDecodeError,csv.Error):raise HTTPException(422,'CSV inválido (UTF-8 obligatorio)')
    if len(rows)>500: raise HTTPException(413,'Máximo 500 filas')
    required={'external_id','source_account_id','destination_account_id','amount','occurred_at'}
    if not rows or not required.issubset(rows[0]):raise HTTPException(422,'Faltan columnas obligatorias')
    results=[]
    for i,row in enumerate(rows,start=2):
        try:
            payload=TxIn(**{k:v for k,v in row.items() if k in TxIn.model_fields and v not in (None,'')})
            results.append(insert_tx(db,payload,user))
        except Exception as exc:
            db.rollback()
            # Importación atómica: ninguna fila se almacena si otra falla.
            if isinstance(exc,HTTPException):raise HTTPException(422,f'Fila {i}: {exc.detail}')
            raise HTTPException(422,f'Fila {i}: datos inválidos')
    db.commit()
    return {'imported':len(results),'alerts':sum(bool(r['alert']) for r in results)}

@app.get('/api/alerts')
def alerts(status:str|None=None,limit:int=Query(100,ge=1,le=300),db:Session=Depends(get_db),user:Profile=Depends(current_user)):
    query=select(Alert)
    if status:query=query.where(Alert.status==status)
    return [serialize(x) for x in db.scalars(query.order_by(Alert.created_at.desc()).limit(limit)).all()]

@app.patch('/api/alerts/{alert_id}')
def update_alert(alert_id:str,data:AlertUpdate,db:Session=Depends(get_db),user:Profile=Depends(require_role('admin','supervisor','analyst'))):
    x=get_or_404(db,Alert,alert_id)
    if x.status=='INVESTIGATING' and data.status=='DISMISSED':raise HTTPException(409,'Cierre primero la investigación')
    x.status=data.status;log(db,user,'UPDATE_STATUS','alert',x.id,{'status':data.status});db.commit();return serialize(x)

@app.get('/api/cases')
def cases(db:Session=Depends(get_db),user:Profile=Depends(current_user)):
    return [serialize(x) for x in db.scalars(select(Case).order_by(Case.updated_at.desc()).limit(200)).all()]

@app.post('/api/cases',status_code=201)
def create_case(data:CaseIn,db:Session=Depends(get_db),user:Profile=Depends(require_role('admin','supervisor','analyst'))):
    alert=get_or_404(db,Alert,data.alert_id)
    if db.scalar(select(Case.id).where(Case.alert_id==alert.id)):raise HTTPException(409,'Esta alerta ya tiene un caso')
    x=Case(alert_id=alert.id,title=data.title,owner_id=user.id,priority=alert.severity)
    db.add(x);db.flush();alert.status='INVESTIGATING';log(db,user,'CREATE','case',x.id,{'alert_id':alert.id});db.commit();return serialize(x)

@app.patch('/api/cases/{case_id}')
def update_case(case_id:str,data:CaseUpdate,db:Session=Depends(get_db),user:Profile=Depends(require_role('admin','supervisor','analyst'))):
    x=get_or_404(db,Case,case_id)
    if data.status.startswith('CLOSED') and (not data.conclusion or len(data.conclusion.strip())<15):raise HTTPException(422,'Para cerrar se requiere una conclusión de al menos 15 caracteres')
    if data.status=='CLOSED_CONFIRMED' and user.role not in ('admin','supervisor'):raise HTTPException(403,'Solo supervisor o administrador puede confirmar un cierre')
    x.status=data.status;x.conclusion=data.conclusion
    alert=get_or_404(db,Alert,x.alert_id)
    if data.status.startswith('CLOSED'):alert.status='DISMISSED' if data.status=='CLOSED_FALSE_POSITIVE' else 'RESOLVED'
    log(db,user,'UPDATE_STATUS','case',x.id,{'status':data.status});db.commit();return serialize(x)

@app.get('/api/cases/{case_id}/notes')
def notes(case_id:str,db:Session=Depends(get_db),user:Profile=Depends(current_user)):
    get_or_404(db,Case,case_id)
    return [serialize(x) for x in db.scalars(select(CaseNote).where(CaseNote.case_id==case_id).order_by(CaseNote.created_at)).all()]

@app.post('/api/cases/{case_id}/notes',status_code=201)
def add_note(case_id:str,data:NoteIn,db:Session=Depends(get_db),user:Profile=Depends(require_role('admin','analyst','supervisor'))):
    x=get_or_404(db,Case,case_id)
    if x.status.startswith('CLOSED'):raise HTTPException(409,'No se puede editar un caso cerrado')
    note=CaseNote(case_id=case_id,author_id=user.id,body=data.body);db.add(note);db.flush();log(db,user,'ADD_NOTE','case',case_id);db.commit();return serialize(note)

@app.get('/api/network')
def network(db:Session=Depends(get_db),user:Profile=Depends(current_user)):
    accounts=db.scalars(select(Account).limit(150)).all()
    txs=db.scalars(select(Transaction).order_by(Transaction.occurred_at.desc()).limit(350)).all()
    return {'nodes':[{'id':a.id,'label':a.code,'customer_id':a.customer_id} for a in accounts], 'edges':[{'source':t.source_account_id,'target':t.destination_account_id,'amount':t.amount,'risk':t.risk_level,'id':t.id} for t in txs]}

@app.get('/api/audit')
def audit(db:Session=Depends(get_db),user:Profile=Depends(require_role('admin','supervisor'))):
    return [serialize(x) for x in db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)).all()]

@app.get('/api/users')
def users(db:Session=Depends(get_db),user:Profile=Depends(require_role('admin'))):
    return [serialize(x) for x in db.scalars(select(Profile).order_by(Profile.created_at)).all()]

@app.patch('/api/users/{user_id}/role')
def set_role(user_id:str,data:RoleUpdate,db:Session=Depends(get_db),user:Profile=Depends(require_role('admin'))):
    target=get_or_404(db,Profile,user_id)
    if target.id==user.id:raise HTTPException(409,'No puedes modificar tu propio rol')
    target.role=data.role;log(db,user,'ASSIGN_ROLE','profile',target.id,{'role':data.role});db.commit();return serialize(target)
