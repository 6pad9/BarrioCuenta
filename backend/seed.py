"""Carga explícita de datos ficticios; nunca se ejecuta al iniciar el servidor."""
from .app import create_app, J, H
from .models import *
from .finance import *
from werkzeug.security import generate_password_hash

def seed(app):
    db=app.config['DB']()
    if db.query(User).count():db.close();return
    stores=[Store(name='Comercial Santa Rosa',district='San Juan de Lurigancho',kind='Bazar'),Store(name='Ferretería El Tornillo',district='Comas',kind='Ferretería')]
    db.add_all(stores);db.flush()
    customers=[Customer(name=n,document=d) for n,d in [('Juan Pérez','45872310'),('Ana Torres','41236587'),('Carlos Rojas','001245789')]]
    db.add_all(customers);db.flush()
    for name,email,role,store,customer in [('Rosa Mendoza','rosa@demo.local','business',stores[0].id,None),('Pedro Salas','pedro@demo.local','business',stores[1].id,None),('Luis Campos','admin@demo.local','system',None,None),('Juan Pérez','juan@demo.local','client',None,customers[0].id)]:
        db.add(User(name=name,email=email,role=role,store_id=store,customer_id=customer,password=generate_password_hash('Barrio2026!')))
    accounts=[]
    for customer,store,limit in [(customers[0],stores[0],'1500'),(customers[1],stores[0],'1200'),(customers[2],stores[0],'500'),(customers[0],stores[1],'1200')]:
        a=Account(store_id=store.id,customer_id=customer.id,email='juan@demo.local' if customer.id==customers[0].id else '',limit=limit,consent=J({'version':'1.0','medium':'Datos ficticios','created':'2026-09-14'}));db.add(a);accounts.append(a)
    db.flush()
    for code,name,stock,cash,credit,modes in [('LIC-003','Licuadora 3 velocidades','3','265','289','single,installments'),('OLL-005','Juego de ollas 5 piezas','1','329','356','single,installments'),('PLA-010','Plancha a vapor','5','139','155','single'),('ARR-005','Arroz extra, bolsa 5 kg','32','23','25','single'),('BAT-001','Batidora manual','8','59','66','single,installments')]:
        db.add(Product(store_id=stores[0].id,code=code,name=name,stock=stock,prices=J({'PEN':{'cash':cash,'credit':credit}}),modes=modes))
    db.add(Product(store_id=stores[1].id,code='MART-01',name='Martillo',stock='10',prices=J({'PEN':{'cash':'25','credit':'30'}})))
    for index,(a,principal,mode,count,purchased) in enumerate([(accounts[0],1000,'installments',3,datetime(2026,9,15,10,32)),(accounts[1],1000,'single',1,datetime(2026,9,15,10,30)),(accounts[2],250,'single',1,datetime(2026,9,22,11,0))]):
        snapshot=simulate(principal,'0.02',purchased,20,26,mode,count)
        snapshot.update(monthly='0.02',late_monthly='0.03',currency='PEN',mode=mode,created=purchased.isoformat())
        s=Sale(store_id=a.store_id,account_id=a.id,purchased=purchased.isoformat(),key=f'seed-sale-{index}',fingerprint=H(f'seed{index}'),mode=mode,snapshot=J(snapshot),items=J([dict(name='Venta histórica de muestra',code='DEMO',quantity='1',price=str(principal),subtotal=str(principal))]));db.add(s);db.flush()
        for row in snapshot['rows']:db.add(Obligation(sale_id=s.id,number=row['number'],due=row['due'],principal=row['principal'],interest=row['interest'],amount=row['amount']))
    db.add(Setting(key='clock',value='2026-09-30T09:15:00'))
    db.add(Audit(store_id=stores[0].id,actor='Sistema',action='DATOS_DE_MUESTRA',detail='Escenario académico cargado explícitamente.',created='2026-09-30T09:00:00'))
    db.commit();db.close()

if __name__=='__main__':
    app=create_app()
    if not app.config['DEV']:raise SystemExit('Los datos de muestra solo se cargan en desarrollo.')
    seed(app);print('Datos ficticios listos. Accesos documentados en README.md.')
