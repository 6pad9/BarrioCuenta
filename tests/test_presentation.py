import unittest,tempfile
from decimal import Decimal
from backend.app import create_app
from backend.models import User,Store,Sale,Payment,Statement
from werkzeug.security import generate_password_hash
from scripts.presentation_demo import prepare_demo
class PresentationTests(unittest.TestCase):
 def test_complete_case_and_idempotent_import(self):
  with tempfile.TemporaryDirectory() as folder:
   app=create_app('sqlite:///'+folder+'/demo.db',True);engine=app.config['ENGINE']
   try:
    result=prepare_demo(engine);self.assertEqual(len(result),2);self.assertEqual(result[1]['cuotas'],['349.28','349.28','349.29']);prepare_demo(engine)
    with app.config['DB']() as db:
     self.assertEqual(db.query(Sale).count(),2);self.assertEqual(db.query(Payment).count(),1);self.assertEqual(db.query(Statement).count(),4)
     store=db.query(Store).one();db.add(User(name='Negocio Demo',email='business@example.test',role='business',store_id=store.id,password=generate_password_hash('DemoPassword2026!')));db.commit()
    c=app.test_client();login=c.post('/api/login',json={'email':'business@example.test','password':'DemoPassword2026!'}).json
    self.assertEqual(c.post('/api/verify',json={'challenge':login['challenge'],'code':login['development_code']}).status_code,200)
    csrf=c.get('/api/me').json['csrf'];accounts=c.get('/api/accounts').json
    paid=next(a for a in accounts if 'Pago único' in a['customer_name']);self.assertEqual(Decimal(paid['used']),0);self.assertEqual(Decimal(paid['available']),3000)
    pending=next(a for a in accounts if 'Tres cuotas' in a['customer_name']);self.assertGreater(Decimal(pending['total']),0)
    payload=dict(account_id=pending['id'],key='demo-api-payment',amount='0.01')
    self.assertEqual(c.post('/api/payments',json=payload,headers={'X-CSRF-Token':csrf}).status_code,400)
    payload['amount']=pending['total'];r=c.post('/api/payments',json=payload,headers={'X-CSRF-Token':csrf});self.assertEqual(r.status_code,200)
    self.assertEqual(c.post('/api/payments',json=payload,headers={'X-CSRF-Token':csrf}).json,r.json);self.assertEqual(len(c.get('/api/statements').json),4)
   finally:engine.dispose()
