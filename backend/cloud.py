"""Render entry point: production configuration and one-time administrator setup."""
import os
from urllib.parse import urlsplit
from sqlalchemy import select,text
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash
from .app import create_app
from .config import database_url,load_local_env
from .models import User,Audit
from datetime import datetime
from zoneinfo import ZoneInfo


def validate_cloud():
    if os.getenv('APP_MODE','production')!='production':
        raise RuntimeError('Render requiere APP_MODE=production.')
    from sqlalchemy.engine import make_url
    url=make_url(database_url())
    if url.get_backend_name()!='postgresql' or not url.host or url.host in ('localhost','127.0.0.1','::1'):
        raise RuntimeError('Configura DATABASE_URL con la conexión PostgreSQL de Neon; no se permite una base local en la nube.')
    if url.query.get('sslmode') not in ('require','verify-ca','verify-full'):
        raise RuntimeError('DATABASE_URL debe conservar sslmode=require o una verificación más estricta.')
    public=os.getenv('PUBLIC_URL') or os.getenv('RENDER_EXTERNAL_URL','')
    parsed=urlsplit(public)
    if parsed.scheme!='https' or not parsed.hostname or parsed.hostname in ('localhost','127.0.0.1') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise RuntimeError('Configura PUBLIC_URL con la dirección HTTPS pública de Render.')
    if os.getenv('MAIL_PROVIDER','brevo')!='brevo' or not os.getenv('BREVO_API_KEY') or '@' not in os.getenv('MAIL_FROM_EMAIL',''):
        raise RuntimeError('Configura MAIL_PROVIDER=brevo, BREVO_API_KEY y MAIL_FROM_EMAIL verificado.')
    return public.rstrip('/')


def bootstrap_admin(app):
    """Only an empty database is initialized. Existing passwords are never reset."""
    with app.config['DB']() as db:
        if app.config['ENGINE'].dialect.name=='postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(4261030)'))
        if db.execute(select(User.id).limit(1)).first():return False
        email=os.getenv('BOOTSTRAP_ADMIN_EMAIL','').strip().lower()
        password=os.getenv('BOOTSTRAP_ADMIN_PASSWORD','')
        if '@' not in email or email.rsplit('@',1)[-1].endswith(('.local','.invalid')):
            raise RuntimeError('La base está vacía: configura BOOTSTRAP_ADMIN_EMAIL con un correo real.')
        if len(password)<12 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
            raise RuntimeError('La base está vacía: configura BOOTSTRAP_ADMIN_PASSWORD con 12 caracteres o más, mayúscula, minúscula y número.')
        user=User(email=email,name=os.getenv('BOOTSTRAP_ADMIN_NAME','Administrador de BarrioCuenta'),role='system',password=generate_password_hash(password),activated=True)
        db.add(user);db.flush()
        db.add(Audit(user_id=user.id,actor=user.name,action='INICIALIZAR_PLATAFORMA',entity='users',entity_id=str(user.id),result='EXITO',detail='Primer administrador creado en una base vacía.',changes='{}',created=datetime.now(ZoneInfo('America/Lima')).replace(tzinfo=None).isoformat()))
        db.commit()
        return True


def create_cloud_app():
    load_local_env()
    public=validate_cloud()
    os.environ['APP_MODE']='production'
    os.environ['PUBLIC_URL']=public
    os.environ.setdefault('MAIL_PROVIDER','brevo')
    os.environ.setdefault('AUTO_PROCESS_CUTS','1')
    app=create_app()
    app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=0)
    bootstrap_admin(app)
    return app
