"""Real HTTP + pooled Neon test, restricted to a named disposable test branch."""
import os,sys,json,argparse,threading,urllib.request,http.cookiejar,urllib.error,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.config import load_local_env,database_url
from backend.app import create_app
from backend.seed import seed
from backend.models import Payment,Sale,Product
from sqlalchemy import text
from sqlalchemy.engine import make_url
from waitress import create_server

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--env',required=True)
    parser.add_argument('--test-branch',required=True)
    args=parser.parse_args()
    if not args.test_branch.startswith('codex-verificacion-'):raise RuntimeError('La prueba exige una rama temporal de verificación.')
    for key in ('DATABASE_URL','DATABASE_URL_UNPOOLED','NEON_BRANCH'):os.environ.pop(key,None)
    load_local_env(args.env)
    if os.getenv('NEON_BRANCH')!=args.test_branch:raise RuntimeError('El archivo no corresponde a la rama temporal solicitada.')
    url=make_url(database_url())
    if not url.host or not url.host.endswith('.neon.tech') or '-pooler.' not in url.host:raise RuntimeError('La prueba debe utilizar la conexión agrupada real de Neon.')
    os.environ.update(APP_MODE='development',MAIL_PROVIDER='local',AUTO_PROCESS_CUTS='1')
    app=create_app();seed(app)
    server=create_server(app,host='127.0.0.1',port=5601,threads=4)
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    jar=http.cookiejar.CookieJar()
    client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    csrf=''
    def request(path,body=None):
        req=urllib.request.Request('http://127.0.0.1:5601/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
        with client.open(req,timeout=30) as response:return json.load(response)
    try:
        assert request('health')['status']=='ok'
        login=request('login',dict(email='rosa@demo.local',password='Barrio2026!'))
        assert request('verify',dict(challenge=login['challenge'],code=login['development_code']))['ok']
        me=request('me');csrf=me['csrf'];assert me['user']['role']=='business'
        assert len(request('accounts'))>=3
        assert len(request('statements'))==3
        key='live-neon-check-sale'
        payload=dict(account_id=1,mode='single',count=1,key=key,items=[dict(id=5,quantity=1)])
        simulation=request('simulate',payload);assert simulation['principal']=='66.00'
        first=request('sales',payload)
        assert request('sales',payload)==first
        assert request('sales/'+str(first['id']))['snapshot']['principal']=='66.00'
        payment=request('payments',dict(account_id=2,amount='1011.27',method='EFECTIVO',key='live-neon-check-payment'))
        assert request('accounts/2')['account']['used']=='0.00'
        request('logout',{})
        with app.config['DB']() as db:
            assert db.query(Sale).filter_by(key=key).count()==1
            assert db.query(Payment).filter_by(id=payment['id']).count()==1
            assert db.execute(text('SELECT current_database()')).scalar()
            from decimal import Decimal
            assert Decimal(db.get(Product,5).stock)==7
        print('Servidor HTTP iniciado en 127.0.0.1:5601: OK')
        print('Neon real: conexión agrupada TLS y esquema por conexión directa: OK')
        print('HTTP: health, login/2FA, cuentas, estados recuperados, simulación, venta idempotente, stock y cobranza persistida: OK')
        print('Datos utilizados: ficticios, solo en la rama temporal '+args.test_branch)
    finally:
        server.close();server.task_dispatcher.shutdown();thread.join(timeout=5)
        app.config['ENGINE'].dispose()

if __name__=='__main__':
    try:main()
    except Exception as error:
        message=re.sub(r'(postgres(?:ql)?(?:\+psycopg)?://)[^\s@]+@',r'\1[credenciales ocultas]@',str(error))
        print(type(error).__name__+': '+message,file=sys.stderr);sys.exit(1)
