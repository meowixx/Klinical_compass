 'use client';
import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { LoaderCircle } from 'lucide-react';
import type { AuthSession } from '@/types';
import { repository, isMock } from '@/services';
import { Login } from './Login';
const loading=()=> <div className="splash" role="status">Загрузка рабочего кабинета…</div>;
const Workspace=dynamic(()=>import('./Workspace').then(module=>module.Workspace),{loading});
const AdminPortal=dynamic(()=>import('./RolePortals').then(module=>module.AdminPortal),{loading});
const PatientPortalReadOnly=dynamic(()=>import('./RolePortals').then(module=>module.PatientPortalReadOnly),{loading});
export function CompassApp(){
  const [session,setSession]=useState<AuthSession|null>(null);
  const [ready,setReady]=useState(false);
  const [authError,setAuthError]=useState('');
  useEffect(()=>{let active=true; async function restore(){
    try {for(const storage of [sessionStorage,localStorage]){
      const raw=storage.getItem('cc-session'); if(!raw)continue;
      try {const parsed=JSON.parse(raw) as AuthSession;
        if(parsed.user?.role){const user=isMock?parsed.user:await repository().getAccount();if(active)setSession({...parsed,user});break;}
      }catch{storage.removeItem('cc-session');}
    }}finally{if(active)setReady(true);}
  } void restore();return()=>{active=false;};},[]);
  useEffect(()=>{function requireLogin(){sessionStorage.removeItem('cc-session');localStorage.removeItem('cc-session');setSession(null);setAuthError('Срок сеанса истёк. Войдите снова.');}window.addEventListener('cc-auth-required',requireLogin);return()=>window.removeEventListener('cc-auth-required',requireLogin);},[]);
  async function logout(){try{await repository().logout();sessionStorage.removeItem('cc-session');localStorage.removeItem('cc-session');setSession(null);setAuthError('');}catch{setAuthError('Не удалось завершить сеанс. Проверьте соединение и повторите выход.');}}
  if(!ready)return <div className="splash"><LoaderCircle className="spin"/>Загрузка рабочей среды…</div>;
  if(!session)return <Login onLogin={(next,remember)=>{sessionStorage.removeItem('cc-session');localStorage.removeItem('cc-session');(remember?localStorage:sessionStorage).setItem('cc-session',JSON.stringify(next));setSession(next);}}/>;
  return <>{session.user.role==='admin'?<AdminPortal onLogout={logout}/>:session.user.role==='patient'?<PatientPortalReadOnly onLogout={logout}/>:<Workspace onLogout={logout}/>} {authError&&<div className="toast" role="alert">{authError}</div>}</>;
}
