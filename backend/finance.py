"""Reglas financieras puras. Moneda en Decimal; fechas del negocio en Lima."""
from decimal import Decimal, ROUND_HALF_UP, localcontext
from datetime import date, datetime, timedelta
from calendar import monthrange

D = Decimal

def decimal(value):
    try:
        result = D(str(value))
        if not result.is_finite():
            raise ValueError()
        return result
    except Exception:
        raise ValueError('Ingrese un número válido.')

def money(value):
    return decimal(value).quantize(D('.01'), rounding=ROUND_HALF_UP)

def month_date(year, month, day):
    return date(year, month, min(day, monthrange(year, month)[1]))

def add_months(day, count, contractual=None):
    index = day.year * 12 + day.month - 1 + count
    return month_date(index // 12, index % 12 + 1, contractual or day.day)

PERIODS = (1,15,30,60,90,120,180,360)

def rate(value, kind='effective', period=360, capitalization=None):
    value, period = decimal(value) / 100, int(period)
    if value < 0 or value > 10 or period not in PERIODS:
        raise ValueError('Tasa o periodo fuera de rango.')
    with localcontext() as ctx:
        ctx.prec = 40
        if kind == 'nominal':
            if capitalization is None or capitalization == '':
                raise ValueError('La tasa nominal requiere capitalización.')
            capitalization = int(capitalization)
            if capitalization not in PERIODS or capitalization > period:
                raise ValueError('La capitalización debe ser válida y no superar el periodo de la tasa.')
            return (1 + value * D(capitalization) / period) ** (D(30) / capitalization) - 1
        if kind != 'effective':
            raise ValueError('Tipo de tasa inválido.')
        return (1 + value) ** (D(30) / period) - 1

def validate_calendar(cut, pay):
    if not 1 <= cut <= 31 or not 1 <= pay <= 31 or (pay > cut and cut > 27):
        raise ValueError('Calendario inválido: si pago supera a corte, corte debe ser 27 o menor.')

def cycle(purchased, cut, pay, cut_time='23:59:59'):
    validate_calendar(cut, pay)
    parts = list(map(int, cut_time.split(':')))
    if len(parts) == 2: parts.append(0)
    if len(parts) != 3:
        raise ValueError('Hora de corte inválida.')
    hh, mm, ss = parts
    if not 0 <= hh < 24 or not 0 <= mm < 60 or not 0 <= ss < 60:
        raise ValueError('Hora de corte inválida.')
    day = month_date(purchased.year, purchased.month, cut)
    closing = datetime.combine(day, datetime.min.time()).replace(hour=hh, minute=mm, second=ss)
    if purchased > closing:
        day = add_months(day, 1, cut)
        closing = datetime.combine(day, closing.time())
    due = month_date(day.year, day.month, pay)
    if due <= day:
        due = add_months(due, 1, pay)
    return closing, due

def simulate(principal, monthly, purchased, cut, pay, mode, count=1, cut_time='23:59:59'):
    principal, monthly, count = money(principal), decimal(monthly), int(count)
    if principal <= 0 or count < 1 or count > 60 or mode not in ('single', 'installments'):
        raise ValueError('Capital, modalidad o número de cuotas inválidos.')
    closing, base = cycle(purchased, cut, pay, cut_time)
    days = (base - purchased.date()).days
    with localcontext() as ctx:
        ctx.prec = 40
        financed = money(principal * (1 + monthly) ** (D(days) / 30))
        if mode == 'single':
            rows = [dict(number=1, due=base.isoformat(), opening=str(principal), interest=str(financed-principal), principal=str(principal), amount=str(financed), balance='0.00')]
            reserve = principal
        else:
            regular = money(financed / count if monthly == 0 else financed * monthly / (1 - (1 + monthly) ** (-count)))
            balance, rows = financed, []
            for k in range(1, count + 1):
                interest = money(balance * monthly)
                amount = money(balance + interest) if k == count else regular
                amort = money(amount - interest)
                new_balance = money(balance - amort)
                rows.append(dict(number=k, due=add_months(base,k,pay).isoformat(), opening=str(balance), interest=str(interest), principal=str(amort), amount=str(amount), balance=str(new_balance)))
                balance = new_balance
            reserve = financed
    return dict(principal=str(principal), financed=str(financed), reserve=str(reserve), grace=days, base=base.isoformat(), cut=closing.isoformat(), rows=rows)

def late_fee(amount, monthly, due, today):
    days = max(0, (today - due).days)
    with localcontext() as ctx:
        ctx.prec = 40
        return money(decimal(amount) * ((1 + decimal(monthly)) ** (D(days)/30)-1))
