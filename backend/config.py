"""Configuración local sin dependencias adicionales; el entorno tiene prioridad."""
import os
from pathlib import Path
from urllib.parse import quote
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]

def load_local_env(path=None):
    paths=[Path(path)] if path else [ROOT / '.env.local',ROOT / '.env']
    for current in paths:
        if not current.is_file():continue
        for line in current.read_text(encoding='utf-8-sig').splitlines():
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line:continue
            key,value=line.split('=',1);key,value=key.strip(),value.strip()
            if key and key.replace('_','').isalnum():
                if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
                os.environ.setdefault(key,value)


def database_url():
    if os.getenv('DATABASE_URL'):
        raw=os.environ['DATABASE_URL'].strip()
        if raw.startswith('postgres://'):raw='postgresql://'+raw[len('postgres://'):]
        url=make_url(raw)
        if url.drivername=='postgresql':url=url.set(drivername='postgresql+psycopg')
        return url.render_as_string(hide_password=False)
    if os.getenv('DATABASE_NAME'):
        user = quote(os.getenv('DATABASE_USER', 'postgres'), safe='')
        password = quote(os.getenv('DATABASE_PASSWORD', ''), safe='')
        host = os.getenv('DATABASE_HOST', '127.0.0.1')
        port = int(os.getenv('DATABASE_PORT', '5432'))
        name = quote(os.environ['DATABASE_NAME'], safe='')
        return f'postgresql+psycopg://{user}:{password}@{host}:{port}/{name}'
    return 'sqlite:///' + str(ROOT / 'barriocuenta.db')

def migration_url():
    raw=os.getenv('DATABASE_URL_UNPOOLED','').strip()
    if raw:
        if raw.startswith('postgres://'):raw='postgresql://'+raw[len('postgres://'):]
        url=make_url(raw)
        if url.drivername=='postgresql':url=url.set(drivername='postgresql+psycopg')
        return url.render_as_string(hide_password=False)
    # Neon names its direct endpoint by removing the documented pooler suffix.
    url=make_url(database_url())
    if url.host and url.host.endswith('.neon.tech'):
        first,rest=url.host.split('.',1)
        if first.endswith('-pooler'):
            return url.set(host=first[:-7]+'.'+rest).render_as_string(hide_password=False)
    return None
