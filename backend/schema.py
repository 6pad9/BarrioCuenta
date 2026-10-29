"""Idempotent schema upgrade. Existing monetary snapshots are never recalculated."""
from sqlalchemy import inspect, text
import json
from datetime import datetime,date
from zoneinfo import ZoneInfo

def local_date(value):
    if isinstance(value,datetime):return value.astimezone(ZoneInfo('America/Lima')).date()
    return date.fromisoformat(str(value)[:10])

ADDITIONS = {
    'customers': {'document_type': "VARCHAR(15) NOT NULL DEFAULT 'OTRO'"},
    'users': {'activated': 'BOOLEAN NOT NULL DEFAULT TRUE', 'portal_consent': "TEXT DEFAULT '{}'"},
    'accounts': {'rate_terms': "TEXT DEFAULT '{}'", 'calendar_history': "TEXT DEFAULT '[]'"},
    'products': {'description': "TEXT DEFAULT ''", 'brand': "VARCHAR(160) DEFAULT ''", 'supplier': "VARCHAR(160) DEFAULT ''", 'image': "TEXT DEFAULT ''"},
    'payments': {'method': "VARCHAR(15) NOT NULL DEFAULT 'NO_REGISTRADO'"},
    'audit': {'user_id': 'INTEGER REFERENCES users(id)', 'entity': "VARCHAR(80) DEFAULT ''", 'entity_id': "VARCHAR(80) DEFAULT ''", 'result': "VARCHAR(10) DEFAULT 'EXITO'", 'changes': "TEXT DEFAULT '{}'", 'source_ip': "VARCHAR(80) DEFAULT ''"},
}

def upgrade(engine, base):
    # PostgreSQL advisory lock also protects simultaneous server/worker startup.
    with engine.begin() as c:
        if engine.dialect.name == 'postgresql':
            c.execute(text('SELECT pg_advisory_xact_lock(4261029)'))
        tables = inspect(c).get_table_names()
        for table, additions in ADDITIONS.items():
            if table not in tables: continue
            columns = {x['name'] for x in inspect(c).get_columns(table)}
            for name, definition in additions.items():
                if name not in columns:
                    c.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))
        if 'accounts' in tables and engine.dialect.name == 'postgresql':
            c.execute(text('ALTER TABLE accounts ALTER COLUMN cut_time TYPE VARCHAR(8)'))
            numeric = {'accounts': {'limit': '12,2','monthly':'20,10','late_monthly':'20,10'}, 'products':{'stock':'10,3'}, 'obligations':{'principal':'12,2','interest':'12,2','amount':'12,2'}, 'payments':{'total':'12,2'}}
            for table, fields in numeric.items():
                current = {x['name']:x['type'] for x in inspect(c).get_columns(table)}
                for field, precision in fields.items():
                    if 'NUMERIC' not in str(current[field]).upper():
                        c.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{field}" TYPE NUMERIC({precision}) USING "{field}"::numeric'))
            constraints = {x['name'] for x in inspect(c).get_unique_constraints('accounts')}
            if 'uq_accounts_id_store' not in constraints:
                c.execute(text('ALTER TABLE accounts ADD CONSTRAINT uq_accounts_id_store UNIQUE (id,store_id)'))
            for table in ('sales','payments'):
                name = 'fk_' + table + '_account_store'
                if name not in {x['name'] for x in inspect(c).get_foreign_keys(table)}:
                    c.execute(text(f'ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY (account_id,store_id) REFERENCES accounts(id,store_id)'))
            for table, fields in {'sales':{'purchased':'America/Lima'},'payments':{'created':'America/Lima'},'audit':{'created':'America/Lima'},'statements':{'cut':'America/Lima'},'tokens':{'expires':'UTC'}}.items():
                current={x['name']:x['type'] for x in inspect(c).get_columns(table)}
                for field,zone in fields.items():
                    if 'TIMESTAMP' not in str(current[field]).upper():
                        c.execute(text(f'''ALTER TABLE "{table}" ALTER COLUMN "{field}" TYPE TIMESTAMPTZ USING "{field}"::timestamp AT TIME ZONE '{zone}' '''))
            if 'DATE' != str(next(x['type'] for x in inspect(c).get_columns('obligations') if x['name']=='due')).upper():
                c.execute(text('ALTER TABLE obligations ALTER COLUMN due TYPE DATE USING due::date'))
        if 'customers' in tables:
            # Preserve document numbers; only replace the old number-only uniqueness.
            if engine.dialect.name == 'postgresql':
                for uq in inspect(c).get_unique_constraints('customers'):
                    if uq['column_names'] == ['document']:
                        c.execute(text('ALTER TABLE customers DROP CONSTRAINT "' + uq['name'] + '"'))
                c.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_identity ON customers(document_type,document)'))
            # Legacy pending invitations must stay reissuable.
            c.execute(text("UPDATE users SET activated=FALSE WHERE id IN (SELECT user_id FROM tokens WHERE kind='invitation')"))
        base.metadata.create_all(c)
        c.execute(text('CREATE TABLE IF NOT EXISTS schema_versions (version INTEGER PRIMARY KEY)'))
        if not c.execute(text('SELECT 1 FROM schema_versions WHERE version=3')).scalar():
            for sale in c.execute(text('SELECT id,items FROM sales')).mappings().all():
                for position,item in enumerate(json.loads(sale['items'])):
                    if c.execute(text('SELECT 1 FROM sale_items WHERE sale_id=:sale AND position=:position'),dict(sale=sale['id'],position=position)).scalar():continue
                    product_id=item.get('id')
                    c.execute(text('INSERT INTO sale_items(sale_id,position,product_id,name,quantity,price,subtotal) VALUES (:sale,:position,:product,:name,:quantity,:price,:subtotal)'),dict(sale=sale['id'],position=position,product=product_id,name=item['name'],quantity=item['quantity'],price=item['price'],subtotal=item['subtotal']))
            for payment in c.execute(text('SELECT id,created,details FROM payments')).mappings().all():
                for row in json.loads(payment['details'])['due']:
                    if c.execute(text('SELECT 1 FROM payment_allocations WHERE payment_id=:payment AND obligation_id=:obligation'),dict(payment=payment['id'],obligation=row['id'])).scalar():continue
                    c.execute(text('INSERT INTO payment_allocations(payment_id,obligation_id,principal,interest,late,late_days) VALUES (:payment,:obligation,:principal,:interest,:late,:days)'),dict(payment=payment['id'],obligation=row['id'],principal=row['principal'],interest=row['interest'],late=row.get('late','0.00'),days=row.get('late_days',max(0,(local_date(payment['created'])-date.fromisoformat(row['due'])).days))))
            for statement in c.execute(text('SELECT id,cut,details FROM statements')).mappings().all():
                for row in json.loads(statement['details'])['rows']:
                    if c.execute(text('SELECT 1 FROM statement_lines WHERE statement_id=:statement AND obligation_id=:obligation'),dict(statement=statement['id'],obligation=row['id'])).scalar():continue
                    c.execute(text('INSERT INTO statement_lines(statement_id,obligation_id,kind,principal,interest,late,late_days) VALUES (:statement,:obligation,:kind,:principal,:interest,:late,:days)'),dict(statement=statement['id'],obligation=row['id'],kind=row.get('kind','OBLIGACION_HISTORICA'),principal=row['principal'],interest=row['interest'],late=row.get('late','0.00'),days=row.get('late_days',max(0,(local_date(statement['cut'])-date.fromisoformat(row['due'])).days))))
            c.execute(text('INSERT INTO schema_versions(version) VALUES (3)'))
        c.execute(text('INSERT INTO schema_versions(version) SELECT 2 WHERE NOT EXISTS (SELECT 1 FROM schema_versions WHERE version=2)'))
