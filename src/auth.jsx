import React,{useState,useId,useRef,useEffect} from 'react';
import {Eye,EyeOff} from 'lucide-react';
export function PasswordInput({value,onChange,...props}){
 const [visible,setVisible]=useState(false);const id=useId();
 return <span className="password-control"><input {...props} id={id} type={visible?'text':'password'} value={value??''} onChange={e=>onChange(e.target.value)}/><button type="button" aria-controls={id} aria-label={visible?'Ocultar contraseña':'Mostrar contraseña'} aria-pressed={visible} onClick={()=>setVisible(!visible)}>{visible?<EyeOff size={18}/>:<Eye size={18}/>}</button></span>;
}
export function PasswordForm({api,token,change=false,onBack,onDone}){
 const [email,setEmail]=useState(''),[current,setCurrent]=useState(''),[password,setPassword]=useState(''),[confirmation,setConfirmation]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const newPassword=!!token||change;
 async function submit(e){e.preventDefault();setBusy(true);setError('');try{
  if(newPassword&&password!==confirmation)throw new Error('Las contraseñas no coinciden.');
  const result=await api('/password/'+(change?'change':token?'reset':'forgot'),newPassword?{token,current_password:current,password,confirmation}:{email});
  if(newPassword){onDone(result.message);}else setMessage(result.message);
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 return <form onSubmit={submit}><h1>{change?'Cambiar mi contraseña':token?'Crea tu nueva contraseña':'Recuperar contraseña'}</h1><p className="subtitle">{newPassword?'Usa al menos 12 caracteres, una mayúscula, una minúscula y un número. Al guardar se cerrarán tus sesiones.':'Escribe el correo de tu cuenta. Te enviaremos un enlace que vence en 15 minutos.'}</p>{error&&<div className="error" role="alert">{error}</div>}{message&&<div className="success" role="status">{message}</div>}{!newPassword?<label className="field"><span>Correo</span><input type="email" required autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)}/></label>:<>{change&&<label className="field"><span>Contraseña actual</span><PasswordInput required autoComplete="current-password" value={current} onChange={setCurrent}/></label>}<label className="field"><span>Nueva contraseña</span><PasswordInput required minLength={12} maxLength={256} autoComplete="new-password" value={password} onChange={setPassword}/></label><label className="field"><span>Confirmar nueva contraseña</span><PasswordInput required minLength={12} maxLength={256} autoComplete="new-password" value={confirmation} onChange={setConfirmation}/></label></>}<div className="modal-actions"><button className="button" type="button" onClick={onBack}>Volver</button><button className="button primary" disabled={busy}>{busy?'Procesando…':newPassword?'Guardar contraseña':'Enviar enlace'}</button></div></form>
}

export function ChangePasswordDialog(props){
 const ref=useRef(null);
 useEffect(()=>{const before=document.activeElement;ref.current.showModal();return()=>before?.focus()},[]);
 return <dialog ref={ref} className="modal" onCancel={props.onBack}><div className="modal-inner"><PasswordForm {...props} change/></div></dialog>;
}
