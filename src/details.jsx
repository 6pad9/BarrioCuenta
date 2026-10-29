import React,{useState,useEffect} from 'react';

export const periods=[{value:1,label:'Diario · 1 día'},{value:15,label:'Quincenal · 15 días'},{value:30,label:'Mensual · 30 días'},{value:60,label:'Bimestral · 60 días'},{value:90,label:'Trimestral · 90 días'},{value:120,label:'Cuatrimestral · 120 días'},{value:180,label:'Semestral · 180 días'},{value:360,label:'Anual · 360 días'}];
export const guidance={
 'Correo':'Usa el correo registrado. El acceso se completa con un código de un solo uso.',
 'Contraseña':'Para una contraseña nueva: mínimo diez caracteres, una mayúscula y un número.',
 'Documento':'Se vincula por tipo y número; el contacto comercial se conserva por tienda.',
 'Stock':'Cantidad disponible con hasta tres decimales. Los servicios no requieren existencias.',
 'Límite de crédito':'Capital máximo comprometido; intereses futuros y mora no consumen el límite.',
 'Máximo de cuotas':'Entre 1 y 60. La gracia no cuenta como cuota; una cuota no equivale a pago único.',
 'Valor (%)':'Tasa no negativa expresada en porcentaje. La moratoria se pacta independientemente.',
 'Periodo':'Periodo al que corresponde el porcentaje; se convierte a tasa efectiva de 30 días.',
 'Capitalización nominal':'Obligatoria para nominal y no mayor que su periodo. No se aplica a efectiva.',
 'Hora de corte':'America/Lima. Incluye el instante indicado, con precisión de segundos.',
 'Día de corte':'Del 1 al 31. Si pago supera a corte, el corte debe ser 27 o menor.',
 'Día de pago':'Primer pago posterior al corte. Si el día no existe, se ajusta a fin de mes.',
 'Moneda':'PEN o USD, sin conversión. Moneda y calendario se bloquean con capital pendiente.'
};

export function Policy(){
 const [policy,setPolicy]=useState(null),[error,setError]=useState('');
 useEffect(()=>{let current=true;fetch('/api/policy').then(r=>{if(!r.ok)throw Error();return r.json()}).then(p=>current&&setPolicy(p)).catch(()=>current&&setError('No se pudo cargar la política. Actualiza antes de aceptar.'));return()=>{current=false}},[]);
 return <details className="policy"><summary>Leer política de tratamiento de datos · versión 2.0</summary>{error?<p role="alert">{error}</p>:policy?<div className="prose"><p><strong>{policy.academic?'Instalación académica con datos ficticios. ':''}Responsable: </strong>{policy.responsible}. {policy.address}. Contacto: {policy.contact}.</p><p><strong>Operador: </strong>{policy.operator}. Contacto: {policy.operator_contact}.</p>{['purpose','retention','rights','security'].map(k=><p key={k}>{policy[k]}</p>)}</div>:<p>Cargando política…</p>}</details>
}

export function ImageField({value,onChange,onError}){
 return <div className="field"><label>Imagen PNG, JPEG o WebP · máximo 1.5 MB<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>{const file=e.target.files?.[0];if(!file)return;if(file.size>1500000){onError('La imagen debe pesar menos de 1.5 MB.');return;}if(!['image/png','image/jpeg','image/webp'].includes(file.type)){onError('Formato de imagen no admitido.');return;}const reader=new FileReader();reader.onload=()=>{onError('');onChange(reader.result)};reader.onerror=()=>onError('No se pudo leer la imagen.');reader.readAsDataURL(file)}}/></label>{value&&<><img className="product-image" src={value} alt="Vista previa del producto"/><button type="button" onClick={()=>onChange('')}>Quitar imagen</button></>}</div>
}

export function Filters({accounts=[],value,onChange,states=false}){
 const set=(key,v)=>onChange({...value,[key]:v});
 return <div className="query-filters" aria-label="Filtros de consulta"><label>Desde<input type="date" value={value.from||''} onChange={e=>set('from',e.target.value)}/></label><label>Hasta<input type="date" value={value.to||''} onChange={e=>set('to',e.target.value)}/></label>{accounts.length>0&&<label>Cliente y cuenta<select value={value.account||''} onChange={e=>set('account',e.target.value)}><option value="">Todos</option>{accounts.map(a=><option value={a.id} key={a.id}>{a.customer_name} · {a.store_name} · {a.currency}</option>)}</select></label>}{states&&<label>Situación histórica<select value={value.status||''} onChange={e=>set('status',e.target.value)}><option value="">Todas</option><option value="balance">Con importe al corte</option><option value="zero">Sin importe al corte</option></select></label>}<button type="button" onClick={()=>onChange({})}>Limpiar filtros</button></div>
}
export function matches(row,filter,dateKey='created'){
 const d=(row[dateKey]||'').slice(0,10);
 return (!filter.from||d>=filter.from)&&(!filter.to||d<=filter.to)&&(!filter.account||row.account_id===Number(filter.account))&&(!filter.status||(filter.status==='zero'?Number(row.details?.total)===0:Number(row.details?.total)>0));
}
export function StatementReport({statement,onClose}){
 const ref=React.useRef(null);useEffect(()=>{const previous=document.activeElement;ref.current.showModal();return()=>previous?.focus()},[]);
 const d=statement.details,fmt=v=>new Intl.NumberFormat('es-PE',{style:'currency',currency:d.currency}).format(Number(v||0));
 return <dialog ref={ref} onCancel={onClose} className="statement-dialog"><div className="row no-print"><button type="button" onClick={()=>window.print()}>Imprimir / guardar como PDF</button><button type="button" onClick={onClose}>Cerrar</button></div><article><h1>Estado de cuenta EC-{statement.id}</h1><p>{d.store||'Tienda de la cuenta'} · {d.customer} · {d.document}</p><p>Moneda: {d.currency} · Corte: {statement.cut.replace('T',' ')} · Vencimiento: {d.due}</p><div className="table-scroll"><table><thead><tr>{['Concepto / compra','Obligación','Vence','Capital','Interés','Base de mora','TEM mora','Días','Mora','Total'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{d.rows.map(r=><tr key={r.id}><td>{r.description||r.kind||'Obligación'}<small>{r.purchased?.slice(0,10)}</small></td><td>V-{r.sale_id} · {r.number}</td><td>{r.due}</td><td>{fmt(r.principal)}</td><td>{fmt(r.interest)}</td><td>{fmt(r.amount)}</td><td>{r.late_monthly!=null?(Number(r.late_monthly)*100).toFixed(5)+' %':'No registrado'}</td><td>{r.late_days??'No registrado'}</td><td>{fmt(r.late)}</td><td>{fmt(Number(r.amount)+Number(r.late))}</td></tr>)}</tbody></table></div>{!d.rows.length&&<p>No hay obligaciones para este corte.</p>}<p>Capital: {fmt(d.total_principal??d.rows.reduce((s,r)=>s+Number(r.principal),0))} · Intereses: {fmt(d.total_interest??d.rows.reduce((s,r)=>s+Number(r.interest),0))} · Mora: {fmt(d.total_late??d.rows.reduce((s,r)=>s+Number(r.late),0))}</p><h2>Total al corte: {fmt(d.total)}</h2><p>Este documento conserva el importe histórico. La cobranza recalcula la mora a la fecha del pago y excluye cuotas futuras.</p></article></dialog>
}
