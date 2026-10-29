"""Local SMTP or Brevo HTTPS transport. Provider errors never expose credentials."""
import json
import os
import smtplib
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DeliveryError(Exception):
    pass


def provider(development):
    name=os.getenv('MAIL_PROVIDER','auto').strip().lower()
    if name=='auto':
        name='brevo' if os.getenv('BREVO_API_KEY') else ('smtp' if os.getenv('SMTP_HOST') else 'local')
    if name not in ('brevo','smtp','local'):
        raise DeliveryError('Proveedor de correo inválido.')
    if name=='local' and not development:
        raise DeliveryError('El buzón local solo está disponible en desarrollo.')
    return name


def development_mailbox(development):
    return development and provider(development)=='local'


def deliver(user,subject,body,development=False):
    name=provider(development)
    try:
        if name=='local':return
        if name=='brevo':
            key=os.getenv('BREVO_API_KEY','').strip()
            sender=os.getenv('MAIL_FROM_EMAIL','').strip()
            if not key or '@' not in sender:raise DeliveryError('Configura el remitente y la clave del correo.')
            payload=dict(sender=dict(name=os.getenv('MAIL_FROM_NAME','BarrioCuenta'),email=sender),to=[dict(email=user.email,name=user.name)],subject=subject,textContent=body)
            req=Request('https://api.brevo.com/v3/smtp/email',data=json.dumps(payload).encode('utf-8'),method='POST',headers={'api-key':key,'accept':'application/json','content-type':'application/json'})
            with urlopen(req,timeout=12) as response:
                if response.status!=201:raise DeliveryError('El proveedor no confirmó el envío del correo.')
        else:
            host=os.getenv('SMTP_HOST')
            if not host:raise DeliveryError('Configura el servidor de correo.')
            msg=EmailMessage();msg['From']=f"{os.getenv('MAIL_FROM_NAME','BarrioCuenta')} <{os.getenv('MAIL_FROM_EMAIL','no-reply@barriocuenta.local')}>";msg['To']=user.email;msg['Subject']=subject;msg.set_content(body)
            with smtplib.SMTP(host,int(os.getenv('SMTP_PORT','1025')),timeout=12) as smtp:
                if os.getenv('SMTP_STARTTLS')=='1':smtp.starttls()
                if os.getenv('SMTP_USER'):smtp.login(os.environ['SMTP_USER'],os.getenv('SMTP_PASSWORD',''))
                smtp.send_message(msg)
    except DeliveryError:
        raise
    except (HTTPError,URLError,OSError,smtplib.SMTPException,ValueError):
        raise DeliveryError('No fue posible enviar el correo. Revisa la configuración del proveedor e intenta nuevamente.') from None
