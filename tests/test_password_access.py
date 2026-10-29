import os,tempfile,unittest
from datetime import datetime,timedelta
from unittest.mock import patch
from backend.app import create_app
from backend.seed import seed
from backend.models import User,Token
from backend.mailer import DeliveryError

class PasswordAccessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=create_app('sqlite:///'+os.path.join(self.tmp.name,'test.db'),True);seed(self.app);self.c=self.app.test_client();self.csrf=''
 def tearDown(self):
  self.app.config['ENGINE'].dispose();self.tmp.cleanup()
 def post(self,path,data):return self.c.post('/api'+path,json=data,headers={'X-CSRF-Token':self.csrf})
 def login(self,email='admin@demo.local',password='Barrio2026!'):
  r=self.post('/login',dict(email=email,password=password)).get_json();self.assertIn('challenge',r)
  self.assertEqual(self.post('/verify',dict(challenge=r['challenge'],code=r['development_code'])).status_code,200)
  self.csrf=self.c.get('/api/me').get_json()['csrf']
 def reset_token(self,email='admin@demo.local'):
  r=self.post('/password/forgot',dict(email=email));self.assertEqual(r.status_code,202);return r.get_json()['development_link'].split('#reset/')[1]
 def test_five_system_admins_and_business_restriction(self):
  self.login()
  for n in range(4):
   r=self.post('/users',dict(name='Admin '+str(n),email=f'admin{n}@example.test',role='system',password='UniquePassword2026!'));self.assertEqual(r.status_code,200)
  users=self.c.get('/api/users').get_json();self.assertEqual(sum(u['role']=='system' for u in users),5)
  self.assertTrue(all(u['store_id'] is None for u in users if u['role']=='system'))
  self.post('/logout',{});self.csrf='';self.login('rosa@demo.local');self.assertEqual(self.post('/users',dict(role='system')).status_code,403)
 def test_reset_single_use_revokes_sessions_and_requires_new_password(self):
  self.login();token=self.reset_token();old=self.c.get_cookie('bc_session').value
  r=self.post('/password/reset',dict(token=token,password='NewPassword2026!',confirmation='NewPassword2026!'));self.assertEqual(r.status_code,200)
  self.assertEqual(self.post('/password/reset',dict(token=token,password='OtherPassword2026!',confirmation='OtherPassword2026!')).status_code,400)
  self.c.set_cookie('bc_session',old);self.assertEqual(self.c.get('/api/me').status_code,401)
  self.c.delete_cookie('bc_session');self.csrf='';self.assertEqual(self.post('/login',dict(email='admin@demo.local',password='Barrio2026!')).status_code,401)
  self.login(password='NewPassword2026!')
 def test_expiry_reissue_confirmation_and_inactive(self):
  first=self.reset_token();second=self.reset_token()
  payload=dict(password='NewPassword2026!',confirmation='NewPassword2026!')
  self.assertEqual(self.post('/password/reset',dict(token=first,**payload)).status_code,400)
  self.assertEqual(self.post('/password/reset',dict(token=second,password='NewPassword2026!',confirmation='Different2026!')).status_code,400)
  with self.app.config['DB']() as db:
   db.query(Token).filter_by(kind='password_reset').first().expires=(datetime.utcnow()-timedelta(seconds=1)).isoformat();db.commit()
  self.assertEqual(self.post('/password/reset',dict(token=second,**payload)).status_code,400)
  with self.app.config['DB']() as db:
   db.query(User).filter_by(email='admin@demo.local').first().activated=False;db.commit()
  self.assertNotIn('development_link',self.post('/password/forgot',dict(email='admin@demo.local')).get_json())
 def test_change_current_password_and_csrf(self):
  self.login();payload=dict(current_password='wrong',password='NewPassword2026!',confirmation='NewPassword2026!')
  self.assertEqual(self.c.post('/api/password/change',json=payload).status_code,403)
  self.assertEqual(self.post('/password/change',payload).status_code,401)
  payload['current_password']='Barrio2026!';self.assertEqual(self.post('/password/change',payload).status_code,200);self.assertEqual(self.c.get('/api/me').status_code,401)
 def test_production_generic_response_and_mail_failure(self):
  with patch.dict(os.environ,{'APP_MODE':'production','MAIL_PROVIDER':'brevo'}):
   app=create_app('sqlite:///'+os.path.join(self.tmp.name,'prod.db'),True);seed(app);c=app.test_client()
   with patch('backend.app.deliver') as send:
    a=c.post('/api/password/forgot',json=dict(email='admin@demo.local'));b=c.post('/api/password/forgot',json=dict(email='absent@example.test'))
    self.assertEqual(a.status_code,b.status_code);self.assertEqual(a.get_json(),b.get_json());self.assertEqual(send.call_count,1)
   with patch('backend.app.deliver',side_effect=DeliveryError('Unavailable')):
    self.assertEqual(c.post('/api/password/forgot',json=dict(email='admin@demo.local')).get_json(),b.get_json())
   app.config['ENGINE'].dispose()
 def test_request_throttled(self):
  for n in range(8):self.assertEqual(self.post('/password/forgot',dict(email=f'absent{n}@example.test')).status_code,202)
  self.assertEqual(self.post('/password/forgot',dict(email='other@example.test')).status_code,429)
