"""Escenario académico explícito. No se ejecuta al iniciar la aplicación."""
import json,hashlib
from datetime import datetime,date
from decimal import Decimal as D
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.models import Store,Customer,Account,Product,Sale,SaleItem,Obligation,Statement,StatementLine,Payment,PaymentAllocation,Audit
from backend.finance import simulate,money,late_fee
J=lambda x:json.dumps(x,ensure_ascii=False)

def prepare_demo(engine):
 now=datetime.now(ZoneInfo('America/Lima')).replace(tzinfo=None)
 purchased=datetime(2026,9,15,10,32)
 if now.date()<date(2026,10,26):raise ValueError('El escenario requiere una fecha posterior al 26/10/2026.')
 result=[]
 with Session(engine) as db,db.begin():
  store=db.scalar(select(Store).where(Store.name.in_(['Mi Tienda Test','DEMO - Presentación final'])).with_for_update())
  if not store:
   store=Store(name='DEMO - Presentación final',kind='Bazar académico',district='San Miguel');db.add(store);db.flush()
  product=db.scalar(select(Product).where(Product.store_id==store.id,Product.code=='DEMO-EXPO-KIT'))
  if not product:
   product=Product(store_id=store.id,code='DEMO-EXPO-KIT',name='Kit de exposición (DEMO)',stock='20',prices=J({'PEN':{'cash':'950.00','credit':'1000.00'}}),description='Bien ficticio para demostrar cálculo y cobranza.');db.add(product);db.flush()
  for index,mode in enumerate(['single','installments'],1):
   key=f'demo-expo-2026-sale-{index}'
   sale=db.scalar(select(Sale).where(Sale.store_id==store.id,Sale.key==key))
   if sale:
    result.append({'venta':sale.id,'cuenta':sale.account_id,'modalidad':mode,'existente':True});continue
   doc=f'DEMO-EXPO-{index:02d}'
   customer=db.scalar(select(Customer).where(Customer.document_type=='OTRO',Customer.document==doc))
   if not customer:
    customer=Customer(name='DEMO Presentación - '+('Pago único' if mode=='single' else 'Tres cuotas'),document_type='OTRO',document=doc);db.add(customer);db.flush()
   account=db.scalar(select(Account).where(Account.store_id==store.id,Account.customer_id==customer.id,Account.currency=='PEN'))
   if not account:
    account=Account(store_id=store.id,customer_id=customer.id,currency='PEN',limit='3000',monthly='.02',late_monthly='.03',cut_day=20,pay_day=26,email='',phone='',consent=J({'version':'2.0','medium':'DATOS_FICTICIOS','created':now.isoformat(),'note':'Simulación académica sin datos personales reales.'}),rate_terms=J({'rate':'2','rate_kind':'effective','rate_period':30,'capitalization':None,'late_rate':'3','late_kind':'effective','late_period':30,'late_capitalization':None}));db.add(account);db.flush()
   snap=simulate('1000','.02',purchased,20,26,mode,3 if mode=='installments' else 1)
   snap.update(monthly='.02',late_monthly='.03',currency='PEN',mode=mode,created=purchased.isoformat(),cut_day=20,pay_day=26,cut_time='23:59:59',rate_terms=json.loads(account.rate_terms))
   items=[dict(id=product.id,name=product.name,code=product.code,quantity='1',price='1000.00',subtotal='1000.00')]
   sale=Sale(store_id=store.id,account_id=account.id,purchased=purchased.isoformat(),key=key,fingerprint=hashlib.sha256(key.encode()).hexdigest(),mode=mode,snapshot=J(snap),items=J(items));db.add(sale);db.flush()
   product.stock=str(D(product.stock)-1)
   db.add(SaleItem(sale_id=sale.id,position=0,product_id=product.id,name=product.name,quantity='1',price='1000',subtotal='1000'))
   obligations=[]
   for row in snap['rows']:
    obligation=Obligation(sale_id=sale.id,number=row['number'],due=row['due'],principal=row['principal'],interest=row['interest'],amount=row['amount']);db.add(obligation);db.flush();obligations.append(obligation)
   for closing in [datetime(2026,9,20,23,59,59),datetime(2026,10,20,23,59,59)]:
    due=closing.date().replace(day=26);rows=[]
    for o in obligations:
     if o.due>due.isoformat():continue
     days=max(0,(closing.date()-date.fromisoformat(o.due)).days)
     rows.append(dict(id=o.id,sale_id=sale.id,number=o.number,due=o.due,principal=o.principal,interest=o.interest,amount=o.amount,paid=False,kind='OBLIGACION_ANTERIOR' if o.due<due.isoformat() else ('COMPRA_PAGO_UNICO' if mode=='single' else 'CUOTA'),purchased=purchased.isoformat(),description=product.name,late_monthly='.03',late_days=days,late=str(late_fee(o.amount,'.03',date.fromisoformat(o.due),closing.date()))))
    details=dict(currency='PEN',store=store.name,customer=customer.name,document=doc,cut=closing.isoformat(),due=due.isoformat(),rows=rows)
    for f in ['principal','interest','late']:details['total_'+f]=str(money(sum((D(r[f]) for r in rows),D(0))))
    details['total']=str(money(sum((D(r['amount'])+D(r['late']) for r in rows),D(0))))
    statement=Statement(account_id=account.id,cut=closing.isoformat(),details=J(details));db.add(statement);db.flush()
    for r in rows:db.add(StatementLine(statement_id=statement.id,obligation_id=r['id'],kind=r['kind'],principal=r['principal'],interest=r['interest'],late=r['late'],late_days=r['late_days']))
   if mode=='single':
    o=obligations[0];late=late_fee(o.amount,'.03',date.fromisoformat(o.due),now.date());total=money(D(o.amount)+late)
    row=dict(id=o.id,sale_id=sale.id,number=o.number,due=o.due,principal=o.principal,interest=o.interest,amount=o.amount,late=str(late),late_days=(now.date()-date.fromisoformat(o.due)).days,late_monthly='.03')
    summary=dict(currency='PEN',used='1000.00',available='2000.00',due=[row],next=dict(due=o.due,amount=o.amount,number=o.number,sale_id=sale.id),total=str(total))
    payment=Payment(store_id=store.id,account_id=account.id,key='demo-expo-2026-payment',total=str(total),created=now.isoformat(),actor='DEMO - Simulación académica',method='EFECTIVO',details=J(summary));db.add(payment);db.flush()
    db.add(PaymentAllocation(payment_id=payment.id,obligation_id=o.id,principal=o.principal,interest=o.interest,late=str(late),late_days=row['late_days']));o.paid=True
   db.add(Audit(store_id=store.id,actor='DEMO - Preparación académica',action='IMPORTAR_ESCENARIO_DEMO',entity='sales',entity_id=str(sale.id),detail='Escenario ficticio importado para exposición; fechas históricas simuladas, no transacciones reales.',created=now.isoformat()))
   result.append({'venta':sale.id,'cuenta':account.id,'modalidad':mode,'capital':snap['principal'],'financiado':snap['financed'],'cuotas':[r['amount'] for r in snap['rows']]})
 return result
