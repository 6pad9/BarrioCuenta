from sqlalchemy import Column, Integer, String, Boolean, Text, UniqueConstraint, ForeignKey, create_engine, event, Numeric, CheckConstraint, ForeignKeyConstraint, Date, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from decimal import Decimal
from sqlalchemy.types import TypeDecorator
from datetime import datetime, date
from zoneinfo import ZoneInfo

class ISODate(TypeDecorator):
    impl=Text
    cache_ok=True
    def load_dialect_impl(self,dialect):
        return dialect.type_descriptor(Date() if dialect.name=='postgresql' else Text())
    def process_bind_param(self,value,dialect):
        if value is None:return None
        parsed=date.fromisoformat(str(value))
        return parsed if dialect.name=='postgresql' else parsed.isoformat()
    def process_result_value(self,value,dialect):
        return value.isoformat() if isinstance(value,date) else value

class ISOTime(TypeDecorator):
    impl=Text
    cache_ok=True
    def __init__(self,zone='America/Lima'):
        self.zone=zone
        super().__init__()
    def load_dialect_impl(self,dialect):
        return dialect.type_descriptor(DateTime(timezone=True) if dialect.name=='postgresql' else Text())
    def process_bind_param(self,value,dialect):
        if value is None:return None
        parsed=datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=ZoneInfo(self.zone))
        return parsed if dialect.name=='postgresql' else parsed.astimezone(ZoneInfo(self.zone)).replace(tzinfo=None).isoformat()
    def process_result_value(self,value,dialect):
        return value.astimezone(ZoneInfo(self.zone)).replace(tzinfo=None).isoformat() if isinstance(value,datetime) else value

class ExactDecimal(TypeDecorator):
    """Exact PostgreSQL numeric; text on SQLite avoids binary floating point."""
    impl = Text
    cache_ok = True
    def __init__(self, precision=12, scale=2):
        self.precision, self.scale = precision, scale
        super().__init__()
    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(Numeric(self.precision,self.scale) if dialect.name == "postgresql" else Text())
    def process_bind_param(self, value, dialect):
        return None if value is None else str(value)
    def process_result_value(self, value, dialect):
        return None if value is None else format(Decimal(str(value)), "f")

Base = declarative_base()

class Store(Base):
    __tablename__='stores'
    id=Column(Integer,primary_key=True)
    name=Column(String(160),nullable=False)
    district=Column(String(160),default='')
    kind=Column(String(80),default='Bazar')
    active=Column(Boolean,default=True)

class User(Base):
    __tablename__='users'
    id=Column(Integer,primary_key=True)
    email=Column(String(200),unique=True,nullable=False)
    name=Column(String(160),nullable=False)
    password=Column(Text,nullable=False)
    role=Column(String(20),nullable=False)
    store_id=Column(Integer,ForeignKey('stores.id'))
    customer_id=Column(Integer,ForeignKey('customers.id'))
    activated=Column(Boolean,default=True,nullable=False)
    portal_consent=Column(Text,default='{}')

class Customer(Base):
    __tablename__='customers'
    id=Column(Integer,primary_key=True)
    __table_args__=(UniqueConstraint('document_type','document'),)
    document_type=Column(String(15),default='DNI',nullable=False)
    document=Column(String(40),nullable=False)
    name=Column(String(160),nullable=False)

class Account(Base):
    __tablename__='accounts'
    __table_args__=(UniqueConstraint('store_id','customer_id','currency'),UniqueConstraint('id','store_id'),)
    id=Column(Integer,primary_key=True)
    store_id=Column(Integer,ForeignKey('stores.id'),nullable=False)
    customer_id=Column(Integer,ForeignKey('customers.id'),nullable=False)
    email=Column(String(200),default='')
    phone=Column(String(60),default='')
    consent=Column(Text,nullable=False)
    currency=Column(String(3),default='PEN')
    limit=Column(ExactDecimal(),default='1500.00')
    monthly=Column(ExactDecimal(20,10),default='0.02')
    late_monthly=Column(ExactDecimal(20,10),default='0.03')
    cut_day=Column(Integer,default=20)
    pay_day=Column(Integer,default=26)
    cut_time=Column(String(8),default='23:59:59')
    rate_terms=Column(Text,default='{}')
    calendar_history=Column(Text,default='[]')
    max_months=Column(Integer,default=6)
    active=Column(Boolean,default=True)

class Product(Base):
    __tablename__='products'
    __table_args__=(UniqueConstraint('store_id','code'),)
    id=Column(Integer,primary_key=True)
    store_id=Column(Integer,ForeignKey('stores.id'),nullable=False)
    code=Column(String(60),nullable=False)
    name=Column(String(160),nullable=False)
    kind=Column(String(20),default='product')
    unit=Column(String(30),default='Unidad')
    stock=Column(ExactDecimal(10,3),default='0')
    prices=Column(Text,default='{}')
    description=Column(Text,default='')
    brand=Column(String(160),default='')
    supplier=Column(String(160),default='')
    image=Column(Text,default='')
    modes=Column(String(40),default='single,installments')
    active=Column(Boolean,default=True)

class Sale(Base):
    __tablename__='sales'
    __table_args__=(UniqueConstraint('store_id','key'),ForeignKeyConstraint(['account_id','store_id'],['accounts.id','accounts.store_id']),)
    id=Column(Integer,primary_key=True)
    store_id=Column(Integer,ForeignKey('stores.id'),nullable=False)
    account_id=Column(Integer,ForeignKey('accounts.id'),nullable=False)
    purchased=Column(ISOTime(),nullable=False)
    key=Column(String(120),nullable=False)
    fingerprint=Column(String(64),nullable=False)
    mode=Column(String(20),nullable=False)
    snapshot=Column(Text,nullable=False)
    items=Column(Text,nullable=False)

class Obligation(Base):
    __tablename__='obligations'
    __table_args__=(UniqueConstraint('sale_id','number'),)
    id=Column(Integer,primary_key=True)
    sale_id=Column(Integer,ForeignKey('sales.id'),nullable=False)
    number=Column(Integer,nullable=False)
    due=Column(ISODate(),nullable=False)
    principal=Column(ExactDecimal(),nullable=False)
    interest=Column(ExactDecimal(),nullable=False)
    amount=Column(ExactDecimal(),nullable=False)
    paid=Column(Boolean,default=False)

class Payment(Base):
    __tablename__='payments'
    __table_args__=(UniqueConstraint('store_id','key'),ForeignKeyConstraint(['account_id','store_id'],['accounts.id','accounts.store_id']),)
    id=Column(Integer,primary_key=True)
    store_id=Column(Integer,ForeignKey('stores.id'),nullable=False)
    account_id=Column(Integer,ForeignKey('accounts.id'),nullable=False)
    key=Column(String(120),nullable=False)
    total=Column(ExactDecimal(),nullable=False)
    created=Column(ISOTime(),nullable=False)
    details=Column(Text,nullable=False)
    actor=Column(String(160),nullable=False)
    method=Column(String(15),default='EFECTIVO',nullable=False)

class Statement(Base):
    __tablename__='statements'
    __table_args__=(UniqueConstraint('account_id','cut'),)
    id=Column(Integer,primary_key=True)
    account_id=Column(Integer,ForeignKey('accounts.id'),nullable=False)
    cut=Column(ISOTime(),nullable=False)
    details=Column(Text,nullable=False)

class Audit(Base):
    __tablename__='audit'
    id=Column(Integer,primary_key=True)
    store_id=Column(Integer,ForeignKey('stores.id'))
    actor=Column(String(160),nullable=False)
    action=Column(String(80),nullable=False)
    user_id=Column(Integer,ForeignKey('users.id'))
    entity=Column(String(80),default='')
    entity_id=Column(String(80),default='')
    result=Column(String(10),default='EXITO')
    changes=Column(Text,default='{}')
    source_ip=Column(String(80),default='')
    detail=Column(Text,nullable=False)
    created=Column(ISOTime(),nullable=False)

class Token(Base):
    __tablename__='tokens'
    id=Column(String(64),primary_key=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    kind=Column(String(20),nullable=False)
    secret=Column(String(128),nullable=False)
    expires=Column(ISOTime('UTC'),nullable=False)
    attempts=Column(Integer,default=0)

class Setting(Base):
    __tablename__='settings'
    key=Column(String(50),primary_key=True)
    value=Column(Text,nullable=False)


class LoginAttempt(Base):
    __tablename__='login_attempts'
    bucket=Column(String(64),primary_key=True)
    count=Column(Integer,nullable=False,default=0)
    window=Column(String(32),nullable=False)

class SaleItem(Base):
    __tablename__='sale_items'
    __table_args__=(UniqueConstraint('sale_id','position'),)
    id=Column(Integer,primary_key=True)
    sale_id=Column(Integer,ForeignKey('sales.id'),nullable=False)
    position=Column(Integer,nullable=False)
    product_id=Column(Integer,ForeignKey('products.id'))
    name=Column(String(160),nullable=False)
    quantity=Column(ExactDecimal(10,3),nullable=False)
    price=Column(ExactDecimal(),nullable=False)
    subtotal=Column(ExactDecimal(),nullable=False)

class PaymentAllocation(Base):
    __tablename__='payment_allocations'
    __table_args__=(UniqueConstraint('payment_id','obligation_id'),)
    id=Column(Integer,primary_key=True)
    payment_id=Column(Integer,ForeignKey('payments.id'),nullable=False)
    obligation_id=Column(Integer,ForeignKey('obligations.id'),nullable=False)
    principal=Column(ExactDecimal(),nullable=False)
    interest=Column(ExactDecimal(),nullable=False)
    late=Column(ExactDecimal(),nullable=False)
    late_days=Column(Integer,nullable=False)

class StatementLine(Base):
    __tablename__='statement_lines'
    __table_args__=(UniqueConstraint('statement_id','obligation_id'),)
    id=Column(Integer,primary_key=True)
    statement_id=Column(Integer,ForeignKey('statements.id'),nullable=False)
    obligation_id=Column(Integer,ForeignKey('obligations.id'),nullable=False)
    kind=Column(String(30),nullable=False)
    principal=Column(ExactDecimal(),nullable=False)
    interest=Column(ExactDecimal(),nullable=False)
    late=Column(ExactDecimal(),nullable=False)
    late_days=Column(Integer,nullable=False)


def database(url,migration_url=None):
    options=dict(future=True,pool_pre_ping=True)
    if url.startswith('sqlite'):options['connect_args']={'check_same_thread':False,'timeout':30}
    else:options.update(pool_size=3,max_overflow=2,pool_recycle=300,connect_args={'connect_timeout':15,'prepare_threshold':None})
    engine=create_engine(url,**options)
    if url.startswith('sqlite'):
        @event.listens_for(engine,'connect')
        def sqlite_setup(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
    from .schema import upgrade
    if migration_url and migration_url!=url:
        migration_engine=create_engine(migration_url,future=True,connect_args={'connect_timeout':15,'prepare_threshold':None})
        try:upgrade(migration_engine,Base)
        finally:migration_engine.dispose()
    else:upgrade(engine, Base)
    return engine,sessionmaker(bind=engine,expire_on_commit=False)
