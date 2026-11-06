from datetime import timedelta
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .models import Transaction

RULES = [
    {'code':'HIGH_AMOUNT','name':'Importe inusualmente elevado','weight':35},
    {'code':'VELOCITY','name':'Alta frecuencia en 24 horas','weight':30},
    {'code':'STRUCTURING','name':'Varias operaciones próximas al umbral de revisión','weight':35},
    {'code':'NEW_COUNTERPARTY','name':'Primera relación transaccional','weight':10},
    {'code':'ROUND_TRIP','name':'Flujo recíproco reciente','weight':40},
]

def evaluate(db: Session, source_id: str, destination_id: str, amount: float, occurred_at):
    # Indicadores heurísticos de demostración, NO equivalen a una tipología confirmada.
    reasons = []
    def flag(code, desc, weight): reasons.append({'code':code, 'description':desc, 'weight':weight})
    if amount >= 20000:
        flag('HIGH_AMOUNT', 'Importe de S/ 20 000 o más; revisar contra perfil del cliente', 35)
    start = occurred_at - timedelta(hours=24)
    prior = db.scalars(select(Transaction).where(Transaction.source_account_id == source_id, Transaction.occurred_at >= start, Transaction.occurred_at < occurred_at)).all()
    if len(prior) >= 4:
        flag('VELOCITY', f'{len(prior)+1} operaciones de origen en menos de 24 horas', 30)
    near = sum(1 for t in prior if 8500 <= t.amount < 10000)
    if 8500 <= amount < 10000 and near >= 2:
        flag('STRUCTURING', 'Tres o más operaciones de importes similares en 24 horas; indicador heurístico, sin umbral legal implícito', 35)
    had_pair = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.source_account_id == source_id, Transaction.destination_account_id == destination_id)) or 0
    if had_pair == 0:
        flag('NEW_COUNTERPARTY', 'No existe relación transaccional anterior entre las cuentas', 10)
    reciprocal = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.source_account_id == destination_id, Transaction.destination_account_id == source_id, Transaction.occurred_at >= occurred_at - timedelta(days=7), Transaction.occurred_at <= occurred_at)) or 0
    if reciprocal:
        flag('ROUND_TRIP', 'Se observaron transferencias en sentido contrario durante los últimos 7 días', 40)
    score = min(100, sum(r['weight'] for r in reasons))
    level = 'CRITICAL' if score >= 75 else 'HIGH' if score >= 50 else 'MEDIUM' if score >= 30 else 'LOW'
    return {'score': score, 'level': level, 'reasons': reasons}
