import os, json, secrets, hashlib, hmac, time, smtplib, base64, re
from datetime import datetime, date, timedelta
from pathlib import Path
from email.message import EmailMessage
from flask import Flask, request, jsonify, g, send_from_directory
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from decimal import InvalidOperation
from datetime import timezone
from zoneinfo import ZoneInfo
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from .models import *
from .finance import *
from .config import load_local_env, database_url, migration_url
from .mailer import deliver, DeliveryError, development_mailbox
from threading import Lock

ROOT=Path(__file__).resolve().parents[1]
J=lambda v:json.dumps(v,ensure_ascii=False,default=str)
H=lambda v:hashlib.sha256(v.encode()).hexdigest()

def create_app(url=None, testing=False):
    if not testing:
        load_local_env()
    app=Flask(__name__,static_folder=None)
    dev=os.getenv('APP_MODE','development')=='development'
    engine,DB=database(url or database_url(),migration_url=None if url else migration_url())
    app.config.update(TESTING=testing,DB=DB,ENGINE=engine,DEV=dev,MAILBOX={})
    app.config['MAX_CONTENT_LENGTH']=3*1024*1024
    security={k:int(os.getenv(k,str(v))) for k,v in dict(LOGIN_MAX_ATTEMPTS=8,LOGIN_WINDOW_SECONDS=300,OTP_SECONDS=300,OTP_MAX_ATTEMPTS=5,SESSION_SECONDS=28800,INVITATION_HOURS=24,RESET_SECONDS=900).items()}
    for value in security.values():
        if value <= 0: raise ValueError('Los parámetros de seguridad deben ser positivos.')
    def now():
        s=g.db.get(Setting,'clock') if dev else None
        return datetime.fromisoformat(s.value) if s and s.value else datetime.now(ZoneInfo('America/Lima')).replace(tzinfo=None)
    def real_now():return datetime.utcnow()
    def fail(message,status=400):
        from werkzeug.exceptions import abort
        abort(status,description=message)
    def audit(action,detail,store=None,entity='',entity_id='',before=None,after=None,result='EXITO'):
        user=getattr(g,'user',None)
        g.db.add(Audit(store_id=store,actor=user.name if user else 'Sistema',user_id=user.id if user else None,action=action,detail=detail,created=now().isoformat(),entity=entity or request.path,entity_id=str(entity_id),result=result,changes=J(dict(before=before,after=after)),source_ip=request.remote_addr or ''))
    def failure_audit(message):
        g.db.rollback()
        if request.path.startswith('/api') and request.method != 'GET':
            audit('RECHAZAR_OPERACION',message,getattr(getattr(g,'user',None),'store_id',None),result='FALLO')
            g.db.commit()
    def body():
        value=request.get_json(silent=True)
        if not isinstance(value,dict): fail('Envía un formulario válido.')
        return value
    def throttle(email):
        bucket=H((request.remote_addr or '')+'|'+email)
        insert=pg_insert if engine.dialect.name=='postgresql' else sqlite_insert
        g.db.execute(insert(LoginAttempt).values(bucket=bucket,count=0,window=real_now().isoformat()).on_conflict_do_nothing(index_elements=['bucket']))
        row=g.db.execute(select(LoginAttempt).where(LoginAttempt.bucket==bucket).with_for_update()).scalar_one()
        if (real_now()-datetime.fromisoformat(row.window)).total_seconds()>=security['LOGIN_WINDOW_SECONDS']:
            row.count=0;row.window=real_now().isoformat()
        blocked=row.count>=security['LOGIN_MAX_ATTEMPTS']
        if not blocked:row.count+=1
        g.db.commit()
        if blocked:fail('Demasiados intentos. Espera antes de volver a intentarlo.',429)
    def challenge_for(user):
        user=lock(User,user.id)
        g.db.query(Token).filter_by(user_id=user.id,kind='challenge').delete()
        code=f'{secrets.randbelow(1000000):06d}';challenge=secrets.token_urlsafe(32)
        g.db.add(Token(id=H(challenge),user_id=user.id,kind='challenge',secret=H(code),expires=(real_now()+timedelta(seconds=security['OTP_SECONDS'])).isoformat()))
        mail(user,'Tu código BarrioCuenta',code)
        audit('ENVIAR_2FA','Código emitido',user.store_id,entity='users',entity_id=user.id)
        g.db.commit()
        result=dict(challenge=challenge,email=user.email,expires=security['OTP_SECONDS'])
        if development_mailbox(dev):result['development_code']=code
        return jsonify(result)

    def lock(model,id):
        return g.db.execute(select(model).where(model.id==id).with_for_update()).scalar_one_or_none()
    def require(role):
        if not g.user:fail('Inicia sesión.',401)
        if g.user.role not in role:fail('No tienes permiso para esta operación.',403)
    def account(id,write=False):
        require(('business',) if write else ('business','client'))
        a=lock(Account,id) if write else g.db.get(Account,id)
        if not a or (g.user.role=='business' and a.store_id!=g.user.store_id) or (g.user.role=='client' and a.customer_id!=g.user.customer_id):fail('Cuenta no encontrada.',404)
        return a
    def commercial(model):
        require(('business',))
        return g.db.query(model).filter_by(store_id=g.user.store_id)
    def filtered(query,model,date_field='created'):
        start=request.args.get('from');end=request.args.get('to')
        if start:
            date.fromisoformat(start);query=query.filter(getattr(model,date_field)>=start)
        if end:
            date.fromisoformat(end);query=query.filter(getattr(model,date_field)<(date.fromisoformat(end)+timedelta(days=1)).isoformat())
        if request.args.get('account_id') and hasattr(model,'account_id'):query=query.filter(model.account_id==int(request.args['account_id']))
        return query
    def obj(model):
        return {c.name:getattr(model,c.name) for c in model.__table__.columns}
    def items_for(a):
        return g.db.query(Obligation,Sale).join(Sale).filter(Sale.account_id==a.id).order_by(Obligation.due,Obligation.id).all()
    def totals(a):
        used=D(0);due=[]
        for o,s in items_for(a):
            if not o.paid:
                used+=decimal(o.principal)
                if o.due<=now().date().isoformat():
                    late=late_fee(o.amount,json.loads(s.snapshot)['late_monthly'],date.fromisoformat(o.due),now().date())
                    due.append(dict(id=o.id,sale_id=s.id,number=o.number,due=o.due,principal=o.principal,interest=o.interest,amount=o.amount,late=str(late),late_days=max(0,(now().date()-date.fromisoformat(o.due)).days),late_monthly=json.loads(s.snapshot)['late_monthly']))
        upcoming=next((dict(due=o.due,amount=o.amount,number=o.number,sale_id=s.id) for o,s in items_for(a) if not o.paid),None)
        return dict(used=str(money(used)),available=str(money(decimal(a.limit)-used)),due=due,next=upcoming,total=str(money(sum((decimal(o['amount'])+decimal(o['late']) for o in due),D(0)))))
    def account_obj(a):
        return dict(obj(a),customer_name=g.db.get(Customer,a.customer_id).name,document=g.db.get(Customer,a.customer_id).document,document_type=g.db.get(Customer,a.customer_id).document_type,rate_terms=json.loads(a.rate_terms or '{}'),store_name=g.db.get(Store,a.store_id).name,**totals(a))
    def mail(user,subject,body):
        try:deliver(user,subject,body,development=dev)
        except DeliveryError as error:fail(str(error),503)
    @app.errorhandler(413)
    @app.errorhandler(415)
    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(429)
    @app.errorhandler(503)
    def errors(e):
        failure_audit(e.description)
        return jsonify(error=e.description),e.code
    @app.errorhandler(ValueError)
    @app.errorhandler(KeyError)
    @app.errorhandler(TypeError)
    @app.errorhandler(InvalidOperation)
    def invalid(e):
        failure_audit('Datos inválidos.');return jsonify(error='Revisa los campos y sus formatos.'),400
    @app.errorhandler(IntegrityError)
    def duplicate(e):
        failure_audit('Conflicto de integridad.');return jsonify(error='Ya existe un registro con esos datos. Actualiza la vista.'),409
    @app.before_request
    def begin():
        g.db=DB();g.user=None;g.token=None
        if request.path.startswith('/api') and request.method in ('POST','PUT','DELETE') and engine.dialect.name=='sqlite':g.db.execute(text('BEGIN IMMEDIATE'))
        cookie=request.cookies.get('bc_session')
        if cookie:
            token=g.db.get(Token,H(cookie))
            if token and token.kind=='session' and token.expires>real_now().isoformat():
                g.user=g.db.get(User,token.user_id);g.token=token
        if request.path.startswith('/api') and request.method in ('POST','PUT','DELETE') and g.user and request.path not in ('/api/login','/api/verify','/api/password/forgot','/api/password/reset'):
            if not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),g.token.secret):fail('La sesión debe actualizarse antes de continuar.',403)
    cuts_lock=Lock()
    last_cuts=[float('-inf')]
    cuts_interval=int(os.getenv('AUTO_CUTS_INTERVAL_SECONDS','60'))
    if cuts_interval<1:raise ValueError('El intervalo de cortes debe ser positivo.')
    @app.before_request
    def catch_up_cuts():
        # A sleeping free service catches up on the next authenticated visit.
        if os.getenv('AUTO_PROCESS_CUTS','0')!='1' or request.method!='GET' or request.path not in ('/api/accounts','/api/statements') or not g.user or g.user.role not in ('business','client'):return
        if time.monotonic()-last_cuts[0]<cuts_interval:return
        with cuts_lock:
            if time.monotonic()-last_cuts[0]<cuts_interval:return
            actor=g.user
            try:
                if engine.dialect.name=='sqlite':
                    g.db.rollback();g.db.execute(text('BEGIN IMMEDIATE'))
                g.user=None
                generate_statements()
                g.db.commit()
                last_cuts[0]=time.monotonic()
            except Exception:
                g.db.rollback()
                raise
            finally:g.user=actor
    @app.teardown_request
    def close(error):
        if hasattr(g,'db'):g.db.close()
    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='same-origin'
        if request.path.startswith('/api'):response.headers['Cache-Control']='no-store'
        return response
    @app.get('/api/health')
    def health():
        try:
            g.db.execute(text('SELECT 1'))
            return jsonify(application='BarrioCuenta',status='ok')
        except Exception:
            g.db.rollback()
            return jsonify(application='BarrioCuenta',status='unavailable'),503
    @app.get('/api/me')
    def me():
        require(('system','business','client'))
        return jsonify(user={k:getattr(g.user,k) for k in ('id','name','email','role','store_id','customer_id')},csrf=g.token.secret,now=now().isoformat(),development=dev,store=obj(g.db.get(Store,g.user.store_id)) if g.user.store_id else None)
    def validate_password(password,confirmation=None):
        if not isinstance(password,str) or not 12<=len(password)<=256 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
            fail('Usa de 12 a 256 caracteres, con mayúscula, minúscula y número.')
        if confirmation is not None and password!=confirmation:fail('Las contraseñas no coinciden.')
    def locked_user(user_id):
        return g.db.execute(select(User).where(User.id==user_id).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    def save_password(user,password,action):
        user.password=generate_password_hash(password)
        g.db.query(Token).filter_by(user_id=user.id).delete(synchronize_session=False)
        audit(action,'Contraseña actualizada; sesiones anteriores cerradas.',user.store_id,entity='users',entity_id=user.id)
        g.db.commit()
        response=jsonify(message='Contraseña actualizada. Inicia sesión con tu nueva contraseña.')
        response.delete_cookie('bc_session');return response
    @app.post('/api/password/forgot')
    def forgot_password():
        email=str(body().get('email','')).strip().lower()[:200]
        throttle('password-reset-ip');throttle('password-reset:'+email)
        response=dict(message='Si el correo tiene una cuenta activa, recibirás un enlace para recuperar tu contraseña. Revisa también el correo no deseado.')
        user=g.db.execute(select(User).where(User.email==email).with_for_update()).scalar_one_or_none()
        if user and user.activated:
            raw=secrets.token_urlsafe(40)
            g.db.query(Token).filter_by(user_id=user.id,kind='password_reset').delete()
            g.db.add(Token(id=H(raw),user_id=user.id,kind='password_reset',secret=H(user.password),expires=(real_now()+timedelta(seconds=security['RESET_SECONDS'])).isoformat()))
            link=os.getenv('PUBLIC_URL','http://127.0.0.1:5000').rstrip('/')+'/#reset/'+raw
            try:deliver(user,'Recupera tu contraseña de BarrioCuenta',f'Abre este enlace para crear una nueva contraseña:\n{link}\nVence en {security["RESET_SECONDS"]//60} minutos y solo puede usarse una vez. Si no lo solicitaste, ignora este correo.',development=dev)
            except DeliveryError:
                g.db.rollback();app.logger.warning('No se pudo enviar un correo de recuperación.');return jsonify(response),202
            audit('SOLICITAR_RECUPERACION','Enlace de recuperación solicitado',user.store_id,entity='users',entity_id=user.id)
            g.db.commit()
            if development_mailbox(dev):response['development_link']=link
        return jsonify(response),202
    @app.post('/api/password/reset')
    def reset_password():
        d=body();token_id=H(str(d.get('token','')));candidate=g.db.get(Token,token_id)
        if not candidate or candidate.kind!='password_reset':fail('El enlace no es válido o ya venció. Solicita uno nuevo.')
        user=locked_user(candidate.user_id)
        token=g.db.execute(select(Token).where(Token.id==token_id).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
        if not user or not user.activated or not token or token.kind!='password_reset' or token.expires<=real_now().isoformat() or not hmac.compare_digest(token.secret,H(user.password)):
            fail('El enlace no es válido o ya venció. Solicita uno nuevo.')
        validate_password(d.get('password'),d.get('confirmation') or '')
        return save_password(user,d['password'],'RECUPERAR_CONTRASENA')
    @app.post('/api/password/change')
    def change_password():
        require(('system','business','client'));d=body();throttle('password-change:'+str(g.user.id));user=locked_user(g.user.id)
        if not check_password_hash(user.password,str(d.get('current_password',''))):fail('La contraseña actual no es correcta.',401)
        validate_password(d.get('password'),d.get('confirmation') or '')
        return save_password(user,d['password'],'CAMBIAR_CONTRASENA')
    @app.post('/api/login')
    def login():
        data=body();email=str(data.get('email','')).strip().lower()
        throttle(email)
        user=g.db.execute(select(User).where(User.email==email).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
        if not user or not user.activated or not check_password_hash(user.password,data.get('password','')):fail('Usuario o contraseña incorrectos.',401)
        g.user=user;audit('LOGIN','Contraseña verificada',user.store_id,entity='users',entity_id=user.id)
        return challenge_for(user)
    @app.post('/api/resend')
    def resend():
        d=body();token_id=H(d.get('challenge',''))
        candidate=g.db.get(Token,token_id)
        if not candidate or candidate.kind!='challenge' or candidate.expires<real_now().isoformat():fail('Inicia sesión nuevamente.',401)
        email=g.db.get(User,candidate.user_id).email
        throttle(email)
        user=g.db.execute(select(User).where(User.email==email).with_for_update()).scalar_one()
        t=g.db.execute(select(Token).where(Token.id==token_id).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
        if not t or t.kind!='challenge' or t.expires<real_now().isoformat():fail('Inicia sesión nuevamente.',401)
        return challenge_for(user)
    @app.post('/api/verify')
    def verify():
        data=body();token_id=H(data.get('challenge',''));candidate=g.db.get(Token,token_id)
        if candidate:lock(User,candidate.user_id)
        t=g.db.execute(select(Token).where(Token.id==token_id).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
        if not t or t.kind!='challenge' or t.expires<real_now().isoformat() or t.attempts>=security['OTP_MAX_ATTEMPTS']:fail('Código vencido o inválido. Inicia sesión nuevamente.',401)
        g.user=g.db.get(User,t.user_id)
        t.attempts+=1
        if not hmac.compare_digest(t.secret,H(data.get('code',''))):g.db.commit();fail('Código incorrecto.',401)
        g.user=g.db.get(User,t.user_id);audit('VERIFICAR_2FA','Segundo factor verificado',g.user.store_id,entity='users',entity_id=g.user.id)
        raw=secrets.token_urlsafe(40);csrf=secrets.token_urlsafe(32)
        g.db.add(Token(id=H(raw),user_id=t.user_id,kind='session',secret=csrf,expires=(real_now()+timedelta(seconds=security['SESSION_SECONDS'])).isoformat()));g.db.delete(t);g.db.commit()
        response=jsonify(ok=True);response.set_cookie('bc_session',raw,httponly=True,secure=not dev or os.getenv('COOKIE_SECURE')=='1',samesite='Strict',max_age=security['SESSION_SECONDS']);return response
    @app.post('/api/logout')
    def logout():
        if g.token:
            audit('LOGOUT','Sesión cerrada',g.user.store_id);g.db.delete(g.token);g.db.commit()
        response=jsonify(ok=True);response.delete_cookie('bc_session');return response
    @app.get('/api/stores')
    def stores():
        require(('system',));return jsonify([dict(obj(s),administrators=[{'id':u.id,'name':u.name,'email':u.email} for u in g.db.query(User).filter_by(store_id=s.id,role='business')]) for s in g.db.query(Store)])
    @app.post('/api/stores')
    def save_store():
        require(('system',));data=body();s=g.db.get(Store,int(data['id'])) if data.get('id') else Store()
        if not s:fail('Tienda no encontrada.',404)
        before=obj(s) if s.id else None
        s.name=str(data['name']).strip();s.district=str(data.get('district',''));s.kind=str(data.get('kind','Bazar'));s.active=bool(data.get('active',True))
        if not s.name:fail('Indica el nombre de la tienda.')
        g.db.add(s);g.db.flush();audit('GUARDAR_TIENDA',f'Tienda {s.id}: {s.name}',entity='stores',entity_id=s.id,before=before,after=obj(s));g.db.commit();return jsonify(obj(s))
    @app.get('/api/products')
    def products():return jsonify([dict(obj(p),prices=json.loads(p.prices)) for p in commercial(Product).order_by(Product.id)])
    @app.post('/api/products')
    def product_save():
        require(('business',))
        data=body();p=commercial(Product).filter_by(id=data['id']).first() if data.get('id') else Product(store_id=g.user.store_id)
        require(('business',))
        if not p:fail('Producto no encontrado.',404)
        if not g.db.get(Store,g.user.store_id).active:fail('La tienda está inactiva.')
        before=obj(p) if p.id else None
        p.name=str(data['name']).strip();p.code=str(data['code']).strip();p.kind=data.get('kind','product');p.unit=data.get('unit','Unidad');p.modes=data.get('modes','single,installments');p.active=bool(data.get('active',True))
        if p.kind not in ('product','service') or not p.name or not p.code or p.modes not in ('single','installments','single,installments'):fail('Verifica nombre, código, tipo y modalidad.')
        for field in ('description','brand','supplier','image'):
            setattr(p,field,str(data.get(field,'')))
        if p.image:
            match=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',p.image)
            if not match:fail('Selecciona una imagen PNG, JPEG o WebP.')
            try:raw_image=base64.b64decode(match[2],validate=True)
            except Exception:fail('Imagen inválida.')
            if len(raw_image)>1500000:fail('La imagen debe pesar menos de 1.5 MB.')
            signatures={'png':raw_image.startswith(b'\x89PNG\r\n\x1a\n'),'jpeg':raw_image.startswith(b'\xff\xd8\xff'),'webp':raw_image[:4]==b'RIFF' and raw_image[8:12]==b'WEBP'}
            if not signatures[match[1]]:fail('El contenido no corresponde al formato de imagen.')
        stock=decimal(data.get('stock','0'))
        if stock<0 or stock!=stock.quantize(D('.001')):fail('Stock inválido; admite hasta tres decimales.')
        p.stock=str(stock if p.kind=='product' else D(0));prices=data.get('prices',{})
        if not prices:fail('Registra al menos una moneda.')
        for currency,price in prices.items():
            if currency not in ('PEN','USD') or money(price['credit'])<=0 or money(price['cash'])<0:fail('Precio o moneda inválidos.')
            price['credit']=str(money(price['credit']));price['cash']=str(money(price['cash']))
        p.prices=J(prices);g.db.add(p);g.db.flush();audit('GUARDAR_PRODUCTO',f'{p.code}: stock {p.stock}',p.store_id,entity='products',entity_id=p.id,before={k:v for k,v in (before or {}).items() if k!='image'},after={k:v for k,v in obj(p).items() if k!='image'});g.db.commit();return jsonify(id=p.id)
    @app.get('/api/accounts')
    def accounts():
        require(('business','client'))
        q=g.db.query(Account).filter_by(**({'store_id':g.user.store_id} if g.user.role=='business' else {'customer_id':g.user.customer_id}))
        return jsonify([account_obj(a) for a in q])
    @app.get('/api/users')
    def users():
        require(('system',))
        return jsonify([{k:getattr(u,k) for k in ('id','name','email','role','store_id')} for u in g.db.query(User).filter(User.role.in_(('system','business')))])
    @app.post('/api/users')
    def create_user():
        require(('system',));d=body();email=str(d.get('email','')).strip().lower();password=d.get('password','');role=d.get('role','business')
        if role not in ('system','business'):fail('Selecciona un perfil de administrador válido.')
        store=None
        if role=='business':
            store=g.db.get(Store,int(d['store_id']))
            if not store or not store.active:fail('Selecciona una tienda activa.')
        if '@' not in email or len(email)>200:fail('Indica un correo válido.')
        validate_password(password)
        u=User(name=str(d.get('name','')).strip(),email=email,role=role,store_id=store.id if store else None,password=generate_password_hash(password))
        if not u.name or len(u.name)>160:fail('Indica un nombre de hasta 160 caracteres.')
        g.db.add(u);g.db.flush();audit('CREAR_ACCESO',f'Administrador {u.id}, perfil {role}',entity='users',entity_id=u.id);g.db.commit();return jsonify(id=u.id)
    @app.post('/api/invitations')
    def invite():
        require(('business',));d=body();a=account(int(d['account_id']),True);email=str(d['email']).strip().lower()
        if '@' not in email:fail('Indica un correo válido.')
        existing=g.db.execute(select(User).where(User.customer_id==a.customer_id).with_for_update()).scalar_one_or_none()
        if existing and existing.activated:fail('El cliente ya tiene acceso al portal. Debe usar su cuenta existente.')
        if existing:
            if existing.email!=email:fail('El reenvío debe usar el correo original de la invitación.')
            u=existing
            g.db.query(Token).filter_by(user_id=u.id,kind='invitation').delete()
        else:
            if g.db.query(User).filter_by(email=email).first():fail('El correo ya tiene un usuario asociado.')
            u=User(name=g.db.get(Customer,a.customer_id).name,email=email,role='client',customer_id=a.customer_id,password=generate_password_hash(secrets.token_urlsafe(64)),activated=False)
            g.db.add(u);g.db.flush()
        raw=secrets.token_urlsafe(40)
        g.db.add(Token(id=H(raw),user_id=u.id,kind='invitation',secret='',expires=(real_now()+timedelta(hours=security['INVITATION_HOURS'])).isoformat()))
        public=os.getenv('PUBLIC_URL','http://127.0.0.1:5000').rstrip('/');link=public+'/#activate/'+raw
        mail(u,'Activa tu portal BarrioCuenta',link);a.email=email;audit('INVITAR_PORTAL',f'Invitación para cuenta {a.id}',a.store_id,entity='accounts',entity_id=a.id);g.db.commit()
        result=dict(message=f'Invitación creada. Vence en {security["INVITATION_HOURS"]} horas.')
        if development_mailbox(dev):result['development_link']=link
        return jsonify(result)
    @app.post('/api/activate')
    def activate():
        d=body();t=g.db.execute(select(Token).where(Token.id==H(d.get('token',''))).with_for_update()).scalar_one_or_none();password=d.get('password','')
        if not t or t.kind!='invitation' or t.expires<real_now().isoformat():fail('Enlace inválido o vencido.')
        u=lock(User,t.user_id)
        if not d.get('consent') or len(password)<10 or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password) or password.lower()==u.email.lower():fail('Acepta la política e ingresa una contraseña de al menos diez caracteres, una mayúscula y un número.')
        u.password=generate_password_hash(password);u.activated=True;u.portal_consent=J(dict(version='2.0',medium='DIGITAL',purpose='Consulta de cuentas propias',created=real_now().isoformat(),actor=u.id));g.db.delete(t);audit('ACTIVAR_PORTAL',f'Cliente {u.customer_id} aceptó política v2.0',entity='users',entity_id=u.id);g.db.commit();return jsonify(ok=True)
    @app.post('/api/accounts')
    def account_save():
        require(('business',));d=body();a=account(d['id'],True) if d.get('id') else Account(store_id=g.user.store_id)
        before=obj(a) if a.id else None
        if not d.get('id'):
            if not d.get('consent'):fail('Registra el consentimiento del cliente.')
            document=str(d['document']).strip();name=str(d['customer_name']).strip()
            if not document or not name:fail('Documento y nombre son obligatorios.')
            document_type=d.get('document_type','DNI')
            if document_type not in ('DNI','CE','PASAPORTE','RUC','OTRO'):fail('Tipo de documento inválido.')
            c=g.db.query(Customer).filter_by(document_type=document_type,document=document).first()
            if not c:c=Customer(name=name,document=document,document_type=document_type);g.db.add(c);g.db.flush()
            elif c.name.casefold()!=name.casefold():fail('Verifique los datos ingresados para el documento.')
            medium=d.get('consent_medium','DIGITAL')
            if medium not in ('DIGITAL','DOCUMENTO_FISICO','VERBAL_REGISTRADO'):fail('Medio de consentimiento inválido.')
            a.customer_id=c.id;a.consent=J(dict(version='2.0',purpose='Administración de ventas al crédito',medium=medium,actor=g.user.name,created=now().isoformat()))
        used=decimal(totals(a)['used']) if a.id else D(0)
        currency=d.get('currency','PEN');cut=int(d.get('cut_day',20));pay=int(d.get('pay_day',26));cut_time=d.get('cut_time','23:59:59');validate_calendar(cut,pay)
        cycle(now(),cut,pay,cut_time)
        if a.id and used>0 and (currency!=a.currency or cut!=a.cut_day or pay!=a.pay_day or cut_time!=a.cut_time):fail('Moneda y calendario bloqueados mientras haya capital pendiente.')
        limit=money(d.get('limit','1500'));months=int(d.get('max_months',6))
        if currency not in ('PEN','USD') or limit<used or limit<=0 or not 1<=months<=60:fail('Verifica moneda, límite y plazo; el límite no puede ser menor al capital utilizado.')
        if a.id and (currency!=a.currency or cut!=a.cut_day or pay!=a.pay_day or cut_time!=a.cut_time):
            history=json.loads(a.calendar_history or '[]')
            history.append(dict(cut_day=a.cut_day,pay_day=a.pay_day,cut_time=a.cut_time,currency=a.currency,until=now().isoformat()))
            a.calendar_history=J(history)
        a.currency=currency;a.limit=str(limit);a.max_months=months;a.cut_day=cut;a.pay_day=pay;a.cut_time=cut_time;a.active=bool(d.get('active',True));a.email=d.get('email','');a.phone=d.get('phone','')
        a.monthly=str(rate(d.get('rate',2),d.get('rate_kind','effective'),d.get('rate_period',30),d.get('capitalization')).quantize(D('0.0000000001')))
        a.late_monthly=str(rate(d.get('late_rate',3),d.get('late_kind','effective'),d.get('late_period',30),d.get('late_capitalization')).quantize(D('0.0000000001')))
        a.rate_terms=J(dict(rate=str(d.get('rate',2)),rate_kind=d.get('rate_kind','effective'),rate_period=int(d.get('rate_period',30)),capitalization=int(d['capitalization']) if d.get('rate_kind')=='nominal' else None,late_rate=str(d.get('late_rate',3)),late_kind=d.get('late_kind','effective'),late_period=int(d.get('late_period',30)),late_capitalization=int(d['late_capitalization']) if d.get('late_kind')=='nominal' else None))
        g.db.add(a);g.db.flush();audit('GUARDAR_CUENTA',f'Cuenta {a.id}: condiciones para ventas nuevas',a.store_id,entity='accounts',entity_id=a.id,before=before,after=obj(a));g.db.commit();return jsonify(account_obj(a))
    def prepare(data):
        a=account(int(data['account_id']),True);store=g.db.get(Store,a.store_id)
        if not a.active or not store.active:fail('Tienda o cuenta inactiva; no permite nuevas ventas.')
        mode=data['mode'];count=int(data.get('count',1)) if mode=='installments' else 1
        if count>a.max_months:fail('El plazo excede el máximo de la cuenta.')
        rows=data.get('items',[])
        if not rows:fail('Agrega al menos un producto.')
        grouped={}
        for row in rows:
            product_id=int(row['id']);quantity=decimal(row['quantity'])
            if quantity<=0 or quantity!=quantity.quantize(D('.001')):fail('Cantidad inválida.')
            grouped[product_id]=grouped.get(product_id,D(0))+quantity
        rows=[dict(id=k,quantity=str(v)) for k,v in grouped.items()]
        principal=D(0);items=[];products=[]
        for row in sorted(rows,key=lambda r:int(r['id'])):
            p=lock(Product,int(row['id']));qty=decimal(row['quantity'])
            if not p or p.store_id!=a.store_id or not p.active:fail('Producto no disponible en esta tienda.')
            if qty<=0 or qty!=qty.quantize(D('.001')):fail('Cantidad inválida.')
            if mode not in p.modes.split(','):fail(f'{p.name} no permite esta modalidad.')
            if p.kind=='product' and qty>decimal(p.stock):fail(f'Stock insuficiente de {p.name}.')
            prices=json.loads(p.prices)
            if a.currency not in prices:fail(f'{p.name} no tiene precio en {a.currency}.')
            price=money(prices[a.currency]['credit']);subtotal=money(qty*price);principal+=subtotal
            items.append(dict(id=p.id,name=p.name,code=p.code,quantity=str(qty),price=str(price),subtotal=str(subtotal)));products.append((p,qty))
        result=simulate(principal,a.monthly,now(),a.cut_day,a.pay_day,mode,count,a.cut_time)
        if decimal(result['reserve'])>decimal(totals(a)['available']):fail('Crédito disponible insuficiente.')
        return a,items,products,dict(result,monthly=a.monthly,late_monthly=a.late_monthly,currency=a.currency,cut_day=a.cut_day,pay_day=a.pay_day,cut_time=a.cut_time,rate_terms=json.loads(a.rate_terms or '{}'),mode=mode,created=now().isoformat())
    @app.post('/api/simulate')
    def simulation():
        a,items,products,result=prepare(body());g.db.rollback();return jsonify(dict(result,items=items))
    @app.post('/api/sales')
    def sale_save():
        require(('business',));d=body();key=d.get('key','')
        if not 8<=len(key)<=120:fail('Falta una clave de operación válida.')
        fingerprint=H(J({k:d[k] for k in ('account_id','mode','count','items')}))
        account(int(d['account_id']),True)
        old=commercial(Sale).filter_by(key=key).first()
        if old:
            if old.fingerprint!=fingerprint:fail('La clave ya corresponde a otra venta.',409)
            return jsonify(id=old.id)
        a,items,products,result=prepare(d)
        for p,qty in products:
            if p.kind=='product':p.stock=str(decimal(p.stock)-qty)
        sale=Sale(store_id=a.store_id,account_id=a.id,purchased=now().isoformat(),key=key,fingerprint=fingerprint,mode=d['mode'],snapshot=J(result),items=J(items));g.db.add(sale);g.db.flush()
        for position,item in enumerate(items):g.db.add(SaleItem(sale_id=sale.id,position=position,product_id=item['id'],name=item['name'],quantity=item['quantity'],price=item['price'],subtotal=item['subtotal']))
        for row in result['rows']:g.db.add(Obligation(sale_id=sale.id,number=row['number'],due=row['due'],principal=row['principal'],interest=row['interest'],amount=row['amount']))
        audit('CONFIRMAR_VENTA',f'Venta {sale.id}: {result["reserve"]} {a.currency}',a.store_id,entity='sales',entity_id=sale.id);g.db.commit();return jsonify(id=sale.id)
    @app.get('/api/sales/<int:id>')
    def sale_detail(id):
        s=g.db.get(Sale,id)
        if not s:fail('Venta no encontrada.',404)
        account(s.account_id)
        return jsonify(dict(obj(s),snapshot=json.loads(s.snapshot),items=json.loads(s.items),obligations=[obj(o) for o in g.db.query(Obligation).filter_by(sale_id=s.id)]))
    @app.get('/api/accounts/<int:id>')
    def detail(id):
        a=account(id);return jsonify(account=account_obj(a),sales=[dict(id=s.id,mode=s.mode,purchased=s.purchased,snapshot=json.loads(s.snapshot)) for s in g.db.query(Sale).filter_by(account_id=id)],payments=[dict(obj(p),details=json.loads(p.details)) for p in g.db.query(Payment).filter_by(account_id=id)])
    @app.post('/api/payments')
    def pay():
        require(('business',));d=body();a=account(int(d['account_id']),True);key=d.get('key','')
        if not 8<=len(key)<=120:fail('Falta una clave de operación válida.')
        method=d.get('method','EFECTIVO')
        if method not in ('EFECTIVO','TRANSFERENCIA'):fail('Medio de pago inválido.')
        old=commercial(Payment).filter_by(key=key).first()
        if old:
            if old.account_id!=a.id or money(d['amount'])!=money(old.total) or old.method!=method:fail('La clave corresponde a otro pago.',409)
            return jsonify(id=old.id)
        summary=totals(a)
        if decimal(summary['total'])<=0:fail('No hay obligaciones exigibles.')
        if money(d['amount'])!=decimal(summary['total']):fail('El importe debe coincidir exactamente con '+summary['total']+'.')
        for row in summary['due']:g.db.get(Obligation,row['id']).paid=True
        p=Payment(store_id=a.store_id,account_id=a.id,key=key,total=summary['total'],created=now().isoformat(),actor=g.user.name,method=method,details=J(dict(summary,currency=a.currency)));g.db.add(p);g.db.flush()
        for row in summary['due']:g.db.add(PaymentAllocation(payment_id=p.id,obligation_id=row['id'],principal=row['principal'],interest=row['interest'],late=row['late'],late_days=row['late_days']))
        audit('REGISTRAR_PAGO',f'Pago {p.id}: {p.total}',a.store_id,entity='payments',entity_id=p.id);g.db.commit();return jsonify(id=p.id)
    @app.get('/api/payments')
    def payments():return jsonify([dict(obj(p),customer_name=g.db.get(Customer,g.db.get(Account,p.account_id).customer_id).name,details=json.loads(p.details)) for p in filtered(commercial(Payment),Payment).order_by(Payment.id.desc())])
    @app.get('/api/audit')
    def audits():
        require(('business','system'));q=g.db.query(Audit)
        q=q.filter(Audit.store_id==g.user.store_id) if g.user.role=='business' else q.filter(Audit.store_id.is_(None))
        return jsonify([obj(a) for a in filtered(q,Audit).order_by(Audit.id.desc()).limit(500)])
    def statement_obj(s):
        details=json.loads(s.details)
        a=g.db.get(Account,s.account_id)
        details.setdefault('store',g.db.get(Store,a.store_id).name)
        details.setdefault('document',g.db.get(Customer,a.customer_id).document)
        for row in details['rows']:
            sale=g.db.get(Sale,row['sale_id']);snapshot=json.loads(sale.snapshot)
            row.setdefault('description',', '.join(item['name'] for item in json.loads(sale.items)))
            row.setdefault('purchased',sale.purchased)
            row.setdefault('late',str(late_fee(row['amount'],snapshot['late_monthly'],date.fromisoformat(row['due']),date.fromisoformat(s.cut[:10]))))
            row.setdefault('late_monthly',snapshot['late_monthly'])
            row.setdefault('late_days',max(0,(date.fromisoformat(s.cut[:10])-date.fromisoformat(row['due'])).days))
        return dict(obj(s),details=details)
    @app.get('/api/statements')
    def statements():
        require(('business','client'))
        ids=[a.id for a in g.db.query(Account).filter_by(**({'store_id':g.user.store_id} if g.user.role=='business' else {'customer_id':g.user.customer_id}))]
        return jsonify([statement_obj(s) for s in filtered(g.db.query(Statement).filter(Statement.account_id.in_(ids)),Statement,'cut').order_by(Statement.cut.desc())])
    def generate_statements():
        count=0
        for account_id in [r[0] for r in g.db.query(Account.id).order_by(Account.id)]:
            a=lock(Account,account_id)
            sales=g.db.query(Sale).filter_by(account_id=a.id).order_by(Sale.purchased,Sale.id).all()
            if not sales:continue
            first=datetime.fromisoformat(sales[0].purchased)
            history=json.loads(a.calendar_history or '[]')
            eras=history+[dict(cut_day=a.cut_day,pay_day=a.pay_day,cut_time=a.cut_time,currency=a.currency,until=None)]
            start=first.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
            for era in eras:
                end=datetime.fromisoformat(era['until']) if era.get('until') else now()+timedelta(microseconds=1)
                closing=month_date(start.year,start.month,era['cut_day'])
                while closing<=min(end,now()).date():
                    hh,mm,*seconds=map(int,era['cut_time'].split(':'))
                    stamp=datetime.combine(closing,datetime.min.time()).replace(hour=hh,minute=mm,second=seconds[0] if seconds else 0)
                    if start<=stamp<end and stamp<=now() and not g.db.query(Statement).filter_by(account_id=a.id,cut=stamp.isoformat()).first():
                        due=month_date(closing.year,closing.month,era['pay_day'])
                        if due<=closing:due=add_months(due,1,era['pay_day'])
                        valid_sales={sale.id for sale in sales if sale.purchased<=stamp.isoformat()}
                        paid_at={row['id']:payment.created for payment in g.db.query(Payment).filter_by(account_id=a.id) for row in json.loads(payment.details)['due']}
                        rows=[]
                        for o,sale in items_for(a):
                            if sale.id not in valid_sales or o.due>due.isoformat() or (o.id in paid_at and paid_at[o.id]<=stamp.isoformat()):continue
                            snapshot=json.loads(sale.snapshot)
                            late_days=max(0,(closing-date.fromisoformat(o.due)).days)
                            rows.append(dict(obj(o),paid=False,kind='OBLIGACION_ANTERIOR' if o.due<due.isoformat() else ('COMPRA_PAGO_UNICO' if sale.mode=='single' else 'CUOTA'),purchased=sale.purchased,description=', '.join(i['name'] for i in json.loads(sale.items)),late_monthly=snapshot['late_monthly'],late_days=late_days,late=str(late_fee(o.amount,snapshot['late_monthly'],date.fromisoformat(o.due),closing))))
                        rows.sort(key=lambda r:(r['purchased'],r['sale_id'],r['number']))
                        details=dict(currency=era['currency'],store=g.db.get(Store,a.store_id).name,customer=g.db.get(Customer,a.customer_id).name,document=g.db.get(Customer,a.customer_id).document,cut=stamp.isoformat(),due=due.isoformat(),rows=rows)
                        for field in ('principal','interest','late'):
                            details['total_'+field]=str(money(sum((decimal(row[field]) for row in rows),D(0))))
                        details['total']=str(money(sum((decimal(row['amount'])+decimal(row['late']) for row in rows),D(0))))
                        statement=Statement(account_id=a.id,cut=stamp.isoformat(),details=J(details));g.db.add(statement);g.db.flush()
                        for row in rows:g.db.add(StatementLine(statement_id=statement.id,obligation_id=row['id'],kind=row['kind'],principal=row['principal'],interest=row['interest'],late=row['late'],late_days=row['late_days']))
                        audit('GENERAR_ESTADO',f'Estado {statement.id} de cuenta {a.id}',a.store_id,entity='statements',entity_id=statement.id)
                        count+=1
                    closing=add_months(closing,1,era['cut_day'])
                start=end
        return count
    app.config['PROCESS_CUTS']=generate_statements
    @app.get('/api/policy')
    def policy():
        return jsonify(version='2.0',academic=dev,responsible=os.getenv('PRIVACY_RESPONSIBLE','Pablo Chumacero (proyecto académico)'),address=os.getenv('PRIVACY_ADDRESS','Referencia académica: UPC San Miguel, Av. La Marina 2810, San Miguel, Lima, Perú. La universidad no es responsable del proyecto.'),contact=os.getenv('PRIVACY_CONTACT','chumaceropablo16@gmail.com'),operator=os.getenv('PRIVACY_OPERATOR','Pablo Chumacero · BarrioCuenta académico'),operator_contact=os.getenv('PRIVACY_OPERATOR_CONTACT','chumaceropablo16@gmail.com'),purpose='Administrar ventas al crédito, obligaciones, cobranza y consulta de cuentas propias. No se usan datos para publicidad ni se comparten deudas entre tiendas.',retention='Se conservan datos mientras sean necesarios para liquidar obligaciones o cumplir un fundamento de conservación documentado. Tras cierre y liquidación se revisan para eliminar o anonimizar lo innecesario. Las pruebas ficticias se eliminan al cerrar la campaña.',rights='Puede solicitar acceso, rectificación, cancelación o supresión y oposición por el canal informado. Se verifica identidad, se registra la solicitud y se comunica respuesta sustentada. La atención es gratuita.',security='Acceso por roles, aislamiento por tienda, segundo factor, sesiones protegidas y auditoría. El correo se necesita para el portal y 2FA; no es requisito para obtener crédito.')
    @app.get('/api/clock')
    def clock_get():
        require(('system',))
        if not dev:fail('Reloj disponible solo en desarrollo.',404)
        return jsonify(now=now().isoformat(),real=(datetime.now(ZoneInfo('America/Lima')).replace(tzinfo=None)).isoformat())
    @app.cli.command('process-cuts')
    def process_cuts():
        """Procesa cortes pendientes. Programar su invocación cada minuto en operación."""
        with app.test_request_context():
            g.db=DB();g.user=None
            try:
                if engine.dialect.name=='sqlite':g.db.execute(text('BEGIN IMMEDIATE'))
                count=generate_statements();g.db.commit();print(f'{count} estados nuevos generados.')
            finally:g.db.close()
    @app.post('/api/clock')
    def clock_set():
        require(('system',))
        if not dev:fail('Reloj disponible solo en desarrollo.',404)
        value=body().get('value','');s=g.db.get(Setting,'clock')
        if value:datetime.fromisoformat(value)
        if not s:s=Setting(key='clock',value=value);g.db.add(s)
        else:s.value=value
        g.db.flush();count=generate_statements();audit('RELOJ_PRUEBAS',f'Fecha {value or "real"}; {count} estados generados');g.db.commit();return jsonify(now=now().isoformat(),generated=count)
    @app.get('/')
    @app.get('/<path:path>')
    def frontend(path=''):
        if path.startswith('api/'):fail('Ruta no encontrada.',404)
        target=ROOT/'dist'/path
        return send_from_directory(ROOT/'dist',path if path and target.is_file() else 'index.html')
    return app

if __name__=='__main__':
    app=create_app();app.run(host='127.0.0.1',port=5000,debug=False)
