"""Copia única SQLite -> PostgreSQL vacío. No modifica el origen ni sobrescribe filas."""
from pathlib import Path
from sqlalchemy import create_engine, select, func, text, inspect, Integer
from .models import Base
from .config import ROOT, load_local_env, database_url

def migrate():
    load_local_env()
    source_path=ROOT/'barriocuenta.db'
    if not source_path.is_file():
        raise RuntimeError('No existe la base local que se desea conservar.')
    target=create_engine(database_url())
    if target.dialect.name!='postgresql':
        raise RuntimeError('El destino debe ser PostgreSQL.')
    source=create_engine('sqlite:///'+str(source_path))
    tables=list(Base.metadata.sorted_tables)
    with target.connect() as connection:
        existing=set(inspect(connection).get_table_names())
        for table in tables:
            if table.name in existing and connection.execute(select(func.count()).select_from(table)).scalar():
                raise RuntimeError('El destino ya contiene datos; no se sobrescribió ningún registro.')
    Base.metadata.create_all(target)
    count=0
    with source.connect() as original, target.begin() as destination:
        for table in tables:
            if table.name=='tokens':
                continue  # Las sesiones temporales no se trasladan.
            rows=[dict(row) for row in original.execute(select(table)).mappings()]
            if not rows:
                continue
            destination.execute(table.insert(),rows)
            count+=len(rows)
            if 'id' in table.c and isinstance(table.c.id.type,Integer):
                destination.execute(text("SELECT setval(pg_get_serial_sequence(:name, 'id'), :value, true)"),dict(name=table.name,value=max(r['id'] for r in rows)))
    source.dispose();target.dispose()
    print(f'Migración completada: {count} registros conservados. SQLite permanece intacto.')

if __name__=='__main__':
    migrate()
