import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
from urllib.error import HTTPError,URLError
from backend.app import create_app
from backend.config import database_url
from backend.cloud import validate_cloud,bootstrap_admin,create_cloud_app
from backend.mailer import deliver,DeliveryError,development_mailbox
from backend.models import User,Statement,Audit,Setting
from backend.seed import seed
from werkzeug.security import check_password_hash


class CloudConfigTests(unittest.TestCase):
    def settings(self):
        return dict(APP_MODE='production',DATABASE_URL='postgresql://owner:p%40ss@ep-example-pooler.neon.tech/neondb?sslmode=require&channel_binding=require',RENDER_EXTERNAL_URL='https://barriocuenta-example.onrender.com',BREVO_API_KEY='FAKE_KEY_FOR_TESTS',MAIL_FROM_EMAIL='sender@example.com')
    def test_neon_url_normalizes_driver_without_losing_ssl_or_password(self):
        with patch.dict(os.environ,self.settings(),clear=True):
            url=database_url()
            self.assertTrue(url.startswith('postgresql+psycopg://'))
            self.assertIn('p%40ss',url)
            self.assertIn('sslmode=require',url)
            self.assertIn('channel_binding=require',url)
            self.assertEqual(validate_cloud(),'https://barriocuenta-example.onrender.com')
    def test_rejects_local_database_development_http_and_missing_credentials(self):
        cases=[dict(DATABASE_URL='sqlite:///:memory:'),dict(APP_MODE='development'),dict(PUBLIC_URL='http://example.com'),dict(DATABASE_URL='postgresql://u:p@neon.example/db'),dict(BREVO_API_KEY=''),dict(PUBLIC_URL='https://example.com/path')]
        for override in cases:
            with self.subTest(override=override),patch.dict(os.environ,dict(self.settings(),**override),clear=True):
                with self.assertRaises(RuntimeError):validate_cloud()
    def test_heroku_style_postgres_prefix(self):
        with patch.dict(os.environ,dict(DATABASE_URL='postgres://u:p@neon.example/db?sslmode=require'),clear=True):
            self.assertEqual(database_url(),'postgresql+psycopg://u:p@neon.example/db?sslmode=require')


class BrevoTests(unittest.TestCase):
    def test_https_payload_and_no_development_code(self):
        response=MagicMock();response.status=201
        with patch.dict(os.environ,dict(MAIL_PROVIDER='brevo',BREVO_API_KEY='FAKE_KEY',MAIL_FROM_EMAIL='sender@example.com'),clear=True),patch('backend.mailer.urlopen') as transport:
            transport.return_value.__enter__.return_value=response
            deliver(SimpleNamespace(email='client@example.com',name='Cliente'),'Verificación','123456',True)
            req=transport.call_args.args[0]
            self.assertEqual(req.full_url,'https://api.brevo.com/v3/smtp/email')
            self.assertEqual(json.loads(req.data)['textContent'],'123456')
            self.assertEqual(json.loads(req.data)['to'][0]['email'],'client@example.com')
            self.assertFalse(development_mailbox(True))
    def test_provider_failure_does_not_expose_key(self):
        for error in (URLError('FAKE_SECRET_FROM_PROVIDER'),HTTPError('https://api.brevo.com',401,'FAKE_SECRET_FROM_PROVIDER',{},None)):
            with patch.dict(os.environ,dict(MAIL_PROVIDER='brevo',BREVO_API_KEY='FAKE_KEY',MAIL_FROM_EMAIL='sender@example.com'),clear=True),patch('backend.mailer.urlopen',side_effect=error):
                with self.assertRaises(DeliveryError) as raised:deliver(SimpleNamespace(email='client@example.com',name='Cliente'),'Código','123456')
                self.assertNotIn('FAKE',str(raised.exception))
    def test_no_local_mailbox_in_production(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(DeliveryError):deliver(SimpleNamespace(email='x@example.com',name='X'),'Código','123456')


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,dict(APP_MODE='production'),clear=True);self.env.start()
        self.app=create_app('sqlite:///'+str(Path(self.temp.name)/'cloud.db'),True)
    def tearDown(self):
        self.app.config['ENGINE'].dispose();self.env.stop();self.temp.cleanup()
    def test_initial_admin_and_redeploy_never_reset_password(self):
        with patch.dict(os.environ,dict(BOOTSTRAP_ADMIN_EMAIL='admin@example.com',BOOTSTRAP_ADMIN_PASSWORD='Private2026Password')):
            self.assertTrue(bootstrap_admin(self.app))
        with patch.dict(os.environ,dict(BOOTSTRAP_ADMIN_EMAIL='other@example.com',BOOTSTRAP_ADMIN_PASSWORD='Changed2026Password')):
            self.assertFalse(bootstrap_admin(self.app))
        with self.app.config['DB']() as db:
            user=db.query(User).one()
            self.assertEqual(user.role,'system')
            self.assertEqual(user.email,'admin@example.com')
            self.assertTrue(check_password_hash(user.password,'Private2026Password'))
            self.assertEqual(db.query(Audit).count(),1)
    def test_missing_or_demo_email_never_creates_user(self):
        for values in ({},dict(BOOTSTRAP_ADMIN_EMAIL='admin@demo.local',BOOTSTRAP_ADMIN_PASSWORD='Private2026Password'),dict(BOOTSTRAP_ADMIN_EMAIL='admin@example.com',BOOTSTRAP_ADMIN_PASSWORD='short')):
            with patch.dict(os.environ,values):
                with self.assertRaises(RuntimeError):bootstrap_admin(self.app)
        with self.app.config['DB']() as db:self.assertEqual(db.query(User).count(),0)
    def test_factory_uses_render_url_production_and_secure_session(self):
        env=CloudConfigTests().settings()
        env.update(BOOTSTRAP_ADMIN_EMAIL='admin@example.com',BOOTSTRAP_ADMIN_PASSWORD='Private2026Password')
        with patch.dict(os.environ,env,clear=True),patch('backend.cloud.create_app',return_value=self.app),patch('backend.cloud.load_local_env'):
            app=create_cloud_app()
            self.assertFalse(app.config['DEV'])
            self.assertEqual(os.environ['PUBLIC_URL'],'https://barriocuenta-example.onrender.com')
            self.assertEqual(os.environ['AUTO_PROCESS_CUTS'],'1')
            with patch('backend.mailer.urlopen') as sender:
                sender.return_value.__enter__.return_value.status=201
                client=app.test_client()
                response=client.post('/api/login',json=dict(email='admin@example.com',password='Private2026Password'),base_url='https://barriocuenta-example.onrender.com')
                self.assertEqual(response.status_code,200)
                self.assertNotIn('development_code',response.json)
                with app.config['DB']() as db:
                    self.assertEqual(db.query(User).count(),1)


class CatchUpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,dict(APP_MODE='development',AUTO_PROCESS_CUTS='1'),clear=True);self.env.start()
        self.app=create_app('sqlite:///'+str(Path(self.temp.name)/'cuts.db'),True);seed(self.app);self.client=self.app.test_client()
        r=self.client.post('/api/login',json=dict(email='rosa@demo.local',password='Barrio2026!')).json
        self.client.post('/api/verify',json=dict(challenge=r['challenge'],code=r['development_code']))
    def tearDown(self):
        self.app.config['ENGINE'].dispose();self.env.stop();self.temp.cleanup()
    def test_authenticated_read_catches_up_and_preserves_actor(self):
        with self.app.config['DB']() as db:self.assertEqual(db.query(Statement).count(),0)
        with patch('backend.app.time.monotonic',return_value=100):
            self.assertEqual(self.client.get('/api/accounts').status_code,200)
            self.assertEqual(self.client.get('/api/statements').status_code,200)
        with self.app.config['DB']() as db:
            self.assertEqual(db.query(Statement).count(),3)
            self.assertTrue(all(a.actor=='Sistema' for a in db.query(Audit).filter_by(action='GENERAR_ESTADO')))
            db.get(Setting,'clock').value='2026-10-30T09:15:00';db.commit()
        with patch('backend.app.time.monotonic',return_value=200):
            self.assertEqual(len(self.client.get('/api/statements').json),6)
        self.assertEqual(self.client.get('/api/me').json['user']['role'],'business')
    def test_anonymous_request_does_not_trigger_work(self):
        anonymous=self.app.test_client()
        self.assertEqual(anonymous.get('/api/statements').status_code,401)
        with self.app.config['DB']() as db:self.assertEqual(db.query(Statement).count(),0)
