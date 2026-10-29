"""Cloud-mode integration against a private PostgreSQL schema; no real email sent."""
import os,sys,json,uuid
from pathlib import Path
from unittest.mock import patch,MagicMock
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app import create_app
from backend.cloud import bootstrap_admin
from backend.config import load_local_env,database_url

def main():
    load_local_env(Path(os.environ['BARRIO_SOURCE_ENV']))
    url=make_url(database_url());engine=create_engine(url)
    schema='bc_cloud_'+uuid.uuid4().hex
    with engine.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
    app=None
    try:
        private=url.update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
        settings=dict(APP_MODE='production',MAIL_PROVIDER='brevo',BREVO_API_KEY='FAKE_KEY',MAIL_FROM_EMAIL='sender@example.com',AUTO_PROCESS_CUTS='1',PUBLIC_URL='https://test.example.com',BOOTSTRAP_ADMIN_EMAIL='admin@example.com',BOOTSTRAP_ADMIN_PASSWORD='Private2026Password')
        with patch.dict(os.environ,settings,clear=True),patch('backend.mailer.urlopen') as transport:
            transport.return_value.__enter__.return_value.status=201
            app=create_app(private,True);assert bootstrap_admin(app)
            def login(email,password):
                client=app.test_client()
                response=client.post('/api/login',base_url='https://test.example.com',json=dict(email=email,password=password))
                assert response.status_code==200,response.json
                assert 'development_code' not in response.json
                code=json.loads(transport.call_args.args[0].data)['textContent']
                verified=client.post('/api/verify',base_url='https://test.example.com',json=dict(challenge=response.json['challenge'],code=code))
                assert verified.status_code==200 and 'Secure' in verified.headers['Set-Cookie']
                csrf=client.get('/api/me',base_url='https://test.example.com').json['csrf']
                return client,{'X-CSRF-Token':csrf}
            admin,headers=login('admin@example.com','Private2026Password')
            store=admin.post('/api/stores',base_url='https://test.example.com',json=dict(name='Negocio ficticio'),headers=headers)
            assert store.status_code==200
            assert admin.post('/api/users',base_url='https://test.example.com',json=dict(name='Comerciante',email='business@example.com',password='Business2026Password',store_id=store.json['id']),headers=headers).status_code==200
            business,headers=login('business@example.com','Business2026Password')
            product=business.post('/api/products',base_url='https://test.example.com',headers=headers,json=dict(name='Producto ficticio',code='CLOUD-01',stock=3,prices={'PEN':{'cash':'10','credit':'12'}}))
            assert product.status_code==200,product.json
            account=business.post('/api/accounts',base_url='https://test.example.com',headers=headers,json=dict(customer_name='Cliente ficticio',document='99999999',document_type='DNI',consent=True))
            assert account.status_code==200,account.json
            sale=business.post('/api/sales',base_url='https://test.example.com',headers=headers,json=dict(account_id=account.json['id'],mode='single',count=1,key='cloud-integration-sale',items=[dict(id=product.json['id'],quantity=1)]))
            assert sale.status_code==200,sale.json
            assert business.get('/api/statements',base_url='https://test.example.com').status_code==200
            assert not bootstrap_admin(app)
            print('Modo nube en PostgreSQL: administrador inicial, 2FA Brevo simulado, tienda, negocio, catálogo, cuenta, venta y recuperación de estados: OK.')
    finally:
        if app:app.config['ENGINE'].dispose()
        with engine.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()

if __name__=='__main__':main()
