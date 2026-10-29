import json
import unittest
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import patch
import test_app
from backend.finance import rate,simulate,cycle
from backend.models import Account,User,Token,Statement,Payment,PaymentAllocation,SaleItem,Audit,Product,LoginAttempt,Obligation,Store

class RequirementFinanceTests(unittest.TestCase):
    def test_all_periods_and_nominal_constraints(self):
        for period in (1,15,30,60,90,120,180,360):
            self.assertGreaterEqual(rate(2,'effective',period),0)
            self.assertGreaterEqual(rate(2,'nominal',period,period),0)
        for cap in (None,'',90):
            with self.assertRaises(ValueError):rate(2,'nominal',30,cap)
    def test_second_boundary(self):
        self.assertEqual(cycle(datetime(2026,9,20,23,59,59),20,26)[1],date(2026,9,26))
        self.assertEqual(cycle(datetime(2026,9,21),20,26)[1],date(2026,10,26))
    def test_document_financial_cases(self):
        cases=[(1000,24,'effective',None,'2026-09-15',20,26,3,'1006.59','347.74','347.75'),(500,18,'effective',None,'2026-09-21',20,26,6,'508.11','88.85','88.85'),(2500,30,'effective',None,'2026-10-05',25,5,4,'2557.12','674.99','675.00'),(900,0,'effective',None,'2026-09-15',20,26,3,'900.00','300.00','300.00'),(1000,24,'nominal',30,'2026-09-15',20,26,3,'1007.29','349.28','349.29'),(1200,36,'nominal',1,'2026-09-21',20,26,6,'1242.72','229.74','229.73'),(800,18,'nominal',90,'2026-10-05',25,5,4,'812.22','210.61','210.62'),(1500,12,'nominal',180,'2026-09-15',20,26,6,'1505.35','259.53','259.53')]
        for p,r,kind,cap,day,cut,pay,n,pg,first,last in cases:
            with self.subTest(principal=p,kind=kind,rate=r):
                result=simulate(p,rate(r,kind,360,cap),datetime.fromisoformat(day),cut,pay,'installments',n)
                self.assertEqual(result['financed'],pg)
                self.assertEqual(result['rows'][0]['amount'],first)
                self.assertEqual(result['rows'][-1]['amount'],last)
                self.assertEqual(result['rows'][-1]['balance'],'0.00')
                for row in result['rows']:
                    self.assertEqual(Decimal(row['interest'])+Decimal(row['principal']),Decimal(row['amount']))
    def test_second_game_and_single_installment(self):
        result=simulate(850,rate(24,'nominal',360,1),datetime(2026,9,21),20,26,'installments',4)
        self.assertEqual(result['financed'],'870.06')
        self.assertEqual([r['amount'] for r in result['rows']],['228.61','228.61','228.61','228.59'])
        self.assertEqual(simulate(1000,'.02',datetime(2026,9,15),20,26,'installments',1)['rows'][0]['amount'],'1027.44')

class RequirementApiTests(test_app.ApiTests):
    def test_terms_and_invalid_nominal(self):
        self.login()
        payload=dict(customer_name='Nuevo',document='80000001',document_type='DNI',consent=True,rate=24,rate_kind='nominal',rate_period=360,late_rate=3)
        self.assertEqual(self.post('/accounts',payload).status_code,400)
        result=self.post('/accounts',dict(payload,capitalization=15))
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json['rate_terms']['capitalization'],15)
        self.assertEqual(result.json['cut_time'],'23:59:59')
        self.assertEqual(self.post('/accounts',dict(payload,capitalization=360,rate_period=30)).status_code,400)
    def test_grouping_and_relational_detail(self):
        self.login()
        payload=dict(account_id=1,mode='single',count=1,key='group-products',items=[dict(id=5,quantity='.250'),dict(id=5,quantity='.750')])
        response=self.post('/sales',payload)
        self.assertEqual(response.status_code,200)
        with self.app.config['DB']() as db:
            row=db.query(SaleItem).filter_by(sale_id=response.json['id']).one()
            self.assertEqual(Decimal(row.quantity),1)
    def test_payment_method_and_allocation(self):
        self.login()
        payload=dict(account_id=2,amount='1011.27',key='transfer-payment',method='CHEQUE')
        self.assertEqual(self.post('/payments',payload).status_code,400)
        payload['method']='TRANSFERENCIA'
        self.assertEqual(self.post('/payments',payload).status_code,200)
        self.assertEqual(self.post('/payments',dict(payload,method='EFECTIVO')).status_code,409)
        with self.app.config['DB']() as db:
            self.assertEqual(db.query(PaymentAllocation).count(),1)
            self.assertEqual(db.query(Payment).one().method,'TRANSFERENCIA')
    def test_client_statements_and_isolation(self):
        self.assertEqual(self.app.test_cli_runner().invoke(args=['process-cuts']).exit_code,0)
        self.login('juan@demo.local')
        response=self.c.get('/api/statements')
        self.assertEqual(response.status_code,200)
        self.assertTrue(all(s['account_id'] in (1,4) for s in response.json))
        self.assertEqual(self.c.get('/api/statements?account_id=2').json,[])
    def test_invitation_reissue_and_invalidation(self):
        self.login()
        first=self.post('/invitations',dict(account_id=3,email='new@demo.local')).json['development_link'].split('#activate/')[1]
        with self.app.config['DB']() as db:
            t=db.query(Token).filter_by(kind='invitation').one();t.expires=(datetime.utcnow()-timedelta(days=1)).isoformat();db.commit()
        second=self.post('/invitations',dict(account_id=3,email='new@demo.local'))
        self.assertEqual(second.status_code,200)
        self.assertEqual(self.post('/activate',dict(token=first,password='NewPassword2026',consent=True)).status_code,400)
        raw=second.json['development_link'].split('#activate/')[1]
        self.assertEqual(self.post('/activate',dict(token=raw,password='NewPassword2026',consent=True)).status_code,200)
        self.assertEqual(self.post('/invitations',dict(account_id=3,email='new@demo.local')).status_code,400)
    def test_resend_invalidates_old_code(self):
        first=self.c.post('/api/login',json=dict(email='rosa@demo.local',password='Barrio2026!')).json
        second=self.c.post('/api/resend',json=dict(challenge=first['challenge']))
        self.assertEqual(second.status_code,200)
        self.assertEqual(self.c.post('/api/verify',json=dict(challenge=first['challenge'],code=first['development_code'])).status_code,401)
        self.assertEqual(self.c.post('/api/verify',json=dict(challenge=second.json['challenge'],code=second.json['development_code'])).status_code,200)
    def test_security_failure_audit_and_persistent_throttle(self):
        for _ in range(8):self.assertEqual(self.c.post('/api/login',json=dict(email='wrong@demo.local',password='bad')).status_code,401)
        self.assertEqual(self.c.post('/api/login',json=dict(email='wrong@demo.local',password='bad')).status_code,429)
        with self.app.config['DB']() as db:
            self.assertEqual(db.query(LoginAttempt).one().count,8)
            self.assertGreater(db.query(Audit).filter_by(result='FALLO').count(),0)
    def test_malformed_json_and_filters(self):
        self.assertEqual(self.c.post('/api/login',json=[]).status_code,400)
        self.login()
        self.assertEqual(self.c.get('/api/payments?from=invalid').status_code,400)
        self.assertEqual(self.post('/products',dict(name='Bad image',code='BAD',image='data:image/svg+xml;base64,AAAA',prices={'PEN':{'cash':1,'credit':1}})).status_code,400)
    def test_calendar_history_survives_change(self):
        self.login();self.post('/payments',dict(account_id=2,amount='1011.27',key='history-payment'))
        a=self.c.get('/api/accounts/2').json['account']
        self.assertEqual(self.post('/accounts',dict(a,cut_day=15,pay_day=25,rate=2,late_rate=3)).status_code,200)
        self.assertEqual(self.app.test_cli_runner().invoke(args=['process-cuts']).exit_code,0)
        rows=self.c.get('/api/statements').json
        original=next(r for r in rows if r['account_id']==2 and r['cut'].startswith('2026-09-20'))
        self.assertEqual(original['details']['total'],'1007.29')
    def test_smtp_transport(self):
        with patch.dict('os.environ',{'SMTP_HOST':'127.0.0.1','SMTP_PORT':'1025'}),patch('backend.app.smtplib.SMTP') as smtp:
            response=self.c.post('/api/login',json=dict(email='rosa@demo.local',password='Barrio2026!'))
            self.assertEqual(response.status_code,200)
            self.assertNotIn('development_code',response.json)
            smtp.return_value.__enter__.return_value.send_message.assert_called_once()
    def test_calendar_credit_service_and_currency_boundaries(self):
        self.login()
        base=dict(customer_name='Frontera',document='90000001',consent=True,rate=2,late_rate=3)
        for cut,pay,expected in [(30,31,400),(27,31,200),(0,26,400),(32,26,400)]:
            response=self.post('/accounts',dict(base,document=str(90000000+cut),cut_day=cut,pay_day=pay))
            self.assertEqual(response.status_code,expected)
        service=self.post('/products',dict(code='SERVICIO',name='Servicio',kind='service',stock=0,prices={'PEN':{'cash':'10','credit':'10'}}))
        self.assertEqual(service.status_code,200)
        self.assertEqual(self.post('/simulate',dict(account_id=1,mode='single',items=[dict(id=service.json['id'],quantity=1)])).status_code,200)
        with self.app.config['DB']() as db:
            a=db.get(Account,3);a.currency='USD';db.commit()
        self.assertEqual(self.post('/simulate',dict(account_id=3,mode='single',items=[dict(id=5,quantity=1)])).status_code,400)
        for n in (0,7):
            self.assertEqual(self.post('/simulate',dict(account_id=1,mode='installments',count=n,items=[dict(id=5,quantity=1)])).status_code,400)
    def test_multiple_due_and_no_future_payment(self):
        self.login()
        with self.app.config['DB']() as db:
            db.add_all([Obligation(sale_id=1,number=10,due='2026-09-30',principal='100',interest='0',amount='100'),Obligation(sale_id=1,number=11,due='2026-09-30',principal='50',interest='0',amount='50')]);db.commit()
        self.assertEqual(self.post('/payments',dict(account_id=1,amount=100,key='incomplete-debt')).status_code,400)
        self.assertEqual(self.post('/payments',dict(account_id=1,amount=150,key='all-matured-debt')).status_code,200)
        with self.app.config['DB']() as db:
            self.assertEqual(db.query(Obligation).filter_by(sale_id=1,paid=True).count(),2)
            self.assertEqual(db.query(Obligation).filter_by(sale_id=1,paid=False).count(),3)
    def test_inactive_store_keeps_history_and_blocks_sales(self):
        self.login('admin@demo.local')
        self.assertEqual(self.post('/stores',dict(id=1,name='Comercial Santa Rosa',active=False)).status_code,200)
        self.post('/logout',{});self.login()
        self.assertEqual(self.post('/simulate',dict(account_id=1,mode='single',items=[dict(id=5,quantity=1)])).status_code,400)
        self.assertEqual(self.c.get('/api/sales/1').status_code,200)
    def test_zero_and_negative_rates_and_stock(self):
        self.login()
        base=dict(customer_name='Sin interés',document='70000001',consent=True,rate=0,late_rate=0)
        self.assertEqual(self.post('/accounts',dict(base,rate=-1)).status_code,400)
        self.assertEqual(self.post('/accounts',base).status_code,200)
        self.assertEqual(self.post('/simulate',dict(account_id=1,mode='single',items=[dict(id=5,quantity='8.001')])).status_code,400)
