import unittest, tempfile, os
from decimal import Decimal as D
from datetime import datetime,date
from backend.finance import simulate,rate,late_fee,cycle,validate_calendar
from backend.app import create_app
from backend.seed import seed
from backend.models import Product,Sale,Payment,Obligation

class FinanceTests(unittest.TestCase):
    def test_reference_french(self):
        s=simulate(1000,'.02',datetime(2026,9,15,10,32),20,26,'installments',3)
        self.assertEqual(s['financed'],'1007.29')
        self.assertEqual([r['amount'] for r in s['rows']],['349.28','349.28','349.29'])
        self.assertEqual(s['rows'][0]['due'],'2026-10-26')
        self.assertEqual(s['rows'][-1]['balance'],'0.00')
    def test_zero_and_rounding(self):
        s=simulate(100,0,datetime(2026,1,1),20,26,'installments',3)
        self.assertEqual([r['amount'] for r in s['rows']],['33.33','33.33','33.34'])
    def test_late(self):
        self.assertEqual(late_fee('1007.29','.03',date(2026,9,26),date(2026,9,30)),D('3.98'))
        self.assertEqual(late_fee('1007.29','.03',date(2026,9,26),date(2026,9,26)),D('0.00'))
    def test_nominal(self):self.assertAlmostEqual(rate(24,'nominal',360,30),D('.02'))
    def test_cut_inclusive(self):
        self.assertEqual(cycle(datetime(2026,9,20,23,59),20,26)[1],date(2026,9,26))
        self.assertEqual(cycle(datetime(2026,9,21),20,26)[1],date(2026,10,26))
    def test_calendar_end_month(self):
        s=simulate(100,'.02',datetime(2026,1,10),20,31,'installments',3)
        self.assertEqual([r['due'] for r in s['rows']],['2026-02-28','2026-03-31','2026-04-30'])
        with self.assertRaises(ValueError):validate_calendar(28,31)

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.app=create_app('sqlite:///'+os.path.join(self.dir.name,'test.db'),True);seed(self.app);self.c=self.app.test_client();self.csrf=''
    def tearDown(self):
        self.app.config['ENGINE'].dispose();self.dir.cleanup()
    def login(self,email='rosa@demo.local'):
        r=self.c.post('/api/login',json={'email':email,'password':'Barrio2026!'}).get_json()
        self.assertEqual(self.c.get('/api/me').status_code,401)
        self.assertEqual(self.c.post('/api/verify',json={'challenge':r['challenge'],'code':r['development_code']}).status_code,200)
        self.csrf=self.c.get('/api/me').get_json()['csrf'];return r
    def post(self,path,body):return self.c.post('/api'+path,json=body,headers={'X-CSRF-Token':self.csrf})
    def test_2fa_one_use_logout_csrf(self):
        challenge=self.login()
        self.assertEqual(self.c.post('/api/logout',json={}).status_code,403)
        self.assertEqual(self.post('/logout',{}).status_code,200)
        self.assertEqual(self.c.get('/api/me').status_code,401)
        self.assertEqual(self.c.post('/api/verify',json={'challenge':challenge['challenge'],'code':challenge['development_code']}).status_code,401)
    def test_cross_store_and_client(self):
        self.login('pedro@demo.local')
        self.assertEqual(self.c.get('/api/accounts/1').status_code,404)
        self.assertEqual(self.post('/payments',{'account_id':2,'amount':'1011.27','key':'cross-key'}).status_code,404)
        self.post('/logout',{});self.login('juan@demo.local')
        ids=[a['id'] for a in self.c.get('/api/accounts').get_json()]
        self.assertEqual(ids,[1,4]);self.assertEqual(self.c.get('/api/accounts/2').status_code,404)
        self.assertEqual(self.post('/simulate',{'account_id':1}).status_code,403)
    def test_system_no_commercial(self):
        self.login('admin@demo.local');self.assertEqual(self.c.get('/api/accounts').status_code,403);self.assertEqual(self.c.get('/api/products').status_code,403)
    def test_payment_exact_and_idempotent(self):
        self.login();payload={'account_id':2,'amount':'1011.27','key':'payment-key-123'}
        self.assertEqual(self.post('/payments',{**payload,'amount':'1000'}).status_code,400)
        first=self.post('/payments',payload);self.assertEqual(first.status_code,200)
        self.assertEqual(self.post('/payments',payload).get_json(),first.get_json())
        self.assertEqual(self.c.get('/api/accounts/2').get_json()['account']['used'],'0.00')
    def test_catalog_modes_and_atomic_sale(self):
        self.login();payload={'account_id':1,'mode':'installments','count':3,'key':'sale-key-123','items':[{'id':3,'quantity':'1'}]}
        self.assertEqual(self.post('/sales',payload).status_code,400)
        payload['items']=[{'id':5,'quantity':'1'}]
        simulation=self.post('/simulate',payload)
        self.assertEqual(simulation.status_code,200)
        self.assertEqual(simulation.get_json()['principal'],'66.00')
        first=self.post('/sales',payload);self.assertEqual(first.status_code,200)
        self.assertEqual(self.post('/sales',payload).get_json(),first.get_json())
        products=self.c.get('/api/products').get_json();self.assertEqual(next(p for p in products if p['id']==5)['stock'],'7')
        self.assertEqual(self.post('/sales',{**payload,'count':4}).status_code,409)
    def test_block_calendar_and_future_payment(self):
        self.login();a=self.c.get('/api/accounts/1').get_json()['account']
        self.assertEqual(self.post('/accounts',{**a,'rate':2,'late_rate':3,'cut_day':19}).status_code,400)
        self.assertEqual(self.post('/payments',{'account_id':1,'amount':'349.28','key':'future-payment'}).status_code,400)
    def test_clock_statements_unique(self):
        self.login('admin@demo.local')
        first=self.post('/clock',{'value':'2026-09-30T09:15:00'}).get_json()
        self.assertEqual(first['generated'],3)
        self.assertEqual(self.post('/clock',{'value':'2026-09-30T09:15:00'}).get_json()['generated'],0)
    def test_invitation_activation_and_customer_scope(self):
        self.login()
        invite=self.post('/invitations',{'account_id':3,'email':'carlos@demo.local'})
        self.assertEqual(invite.status_code,200)
        raw=invite.get_json()['development_link'].split('#activate/')[1]
        payload={'token':raw,'password':'Cliente2026!','consent':True}
        self.assertEqual(self.c.post('/api/activate',json=payload,headers={'X-CSRF-Token':self.csrf}).status_code,200)
        self.assertEqual(self.c.post('/api/activate',json=payload,headers={'X-CSRF-Token':self.csrf}).status_code,400)
        self.post('/logout',{})
        login=self.c.post('/api/login',json={'email':'carlos@demo.local','password':'Cliente2026!'}).get_json()
        self.assertEqual(self.c.post('/api/verify',json={'challenge':login['challenge'],'code':login['development_code']}).status_code,200)
        self.assertEqual([a['id'] for a in self.c.get('/api/accounts').get_json()],[3])
    def test_worker_and_historical_payment(self):
        self.login()
        self.post('/payments',{'account_id':2,'amount':'1011.27','key':'paid-before-worker'})
        result=self.app.test_cli_runner().invoke(args=['process-cuts'])
        self.assertEqual(result.exit_code,0)
        statements=self.c.get('/api/statements').get_json()
        ana=next(s for s in statements if s['account_id']==2)
        self.assertEqual(ana['details']['total'],'1007.29')

if __name__=='__main__':unittest.main()
