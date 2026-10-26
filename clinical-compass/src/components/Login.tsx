'use client';

import { useRef, useState } from 'react';
import { useGSAP } from '@gsap/react';
import gsap from 'gsap';
import { ArrowRight, BarChart3, Bell, Building2, Eye, EyeOff, HeartPulse, LoaderCircle, LockKeyhole, Sparkles, UserRound } from 'lucide-react';
import { Compass, SiteFooter, Logo } from './ui';
import { repository } from '@/services';
import type { AuthSession } from '@/types';

gsap.registerPlugin(useGSAP);

const features = [
  [BarChart3, 'Динамика состояния', 'Дневники и показатели собраны в одной картине'],
  [Bell, 'Сигналы вовремя', 'Врач раньше замечает изменения между визитами'],
  [HeartPulse, 'Непрерывная поддержка', 'Пациент остаётся на связи с клиникой каждый день'],
] as const;

export function Login({ onLogin }: { onLogin: (session: AuthSession, remember: boolean) => void }) {
  const root = useRef<HTMLDivElement>(null);
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [help, setHelp] = useState(false);

  useGSAP(() => {
    const media = gsap.matchMedia();
    media.add({ animate: '(prefers-reduced-motion: no-preference)', desktop: '(min-width: 781px)' }, context => {
      if (!context.conditions?.animate) return;
      const timeline = gsap.timeline({ defaults: { ease: 'power3.out' } });
      timeline
        .from('.login-brand', { autoAlpha: 0, y: -14, duration: 0.55 })
        .from('.login-copy > *:not(.features)', { autoAlpha: 0, y: 24, duration: 0.65, stagger: 0.08 }, '<0.08')
        .from('.feature', { autoAlpha: 0, x: -22, duration: 0.5, stagger: 0.08 }, '<0.16')
        .from('.login-panel', { autoAlpha: 0, x: 30, duration: 0.72 }, 0.12)
        .from('.login-panel > *', { autoAlpha: 0, y: 13, duration: 0.42, stagger: 0.045 }, '<0.18')
        .from('.compass-scene', { autoAlpha: 0, scale: 0.82, rotation: -10, duration: 1 }, 0.08);
      gsap.to('.compass-scene', { y: -10, rotation: 2, duration: 4.8, repeat: -1, yoyo: true, ease: 'sine.inOut' });
      gsap.to('.orbit-dot', { scale: 1.35, autoAlpha: 0.55, duration: 2.2, repeat: -1, yoyo: true, stagger: { each: 0.32, from: 'random' }, ease: 'sine.inOut' });
    });
    return () => media.revert();
  }, { scope: root });

  return <main className="login-page login-redesign" ref={root}>
    <section className="login-visual" aria-label="Возможности Клинического компаса">
      <div className="login-grid" aria-hidden="true"/><div className="login-glow login-glow-one" aria-hidden="true"/><div className="login-glow login-glow-two" aria-hidden="true"/>
      <div className="login-brand"><Logo/></div>
      <div className="login-copy">
        <span className="login-kicker"><Sparkles size={15}/>Цифровое наблюдение между визитами</span>
        <h1>Здоровье<br/>в поле зрения.</h1>
        <p className="login-lead">Данные пациента превращаются в понятную динамику, а врачу проще вовремя увидеть то, что требует внимания.</p>
        <div className="features">{features.map(([Icon,title,description])=><article className="feature" key={title}><span className="feature-icon"><Icon size={22}/></span><div><h2 className="feature-title">{title}</h2><p>{description}</p></div></article>)}</div>
      </div>
      <div className="compass-scene" aria-hidden="true"><span className="compass-halo"/><Compass large/><span className="orbit-dot dot-one"/><span className="orbit-dot dot-two"/><span className="orbit-dot dot-three"/></div>
      <p className="visual-caption">Технологии, которые помогают оставаться рядом.</p>
    </section>
    <section className="login-form-side">
      <div className="login-form-brand"><Logo/></div>
      <div className="login-panel">
        <div className="login-panel-mark"><Building2 size={20}/><span>Единое пространство клиники</span></div>
        <h2>Добро пожаловать</h2><p className="login-subtitle">Введите данные учётной записи, чтобы открыть кабинет.</p>
        <form onSubmit={async event=>{event.preventDefault();setBusy(true);setError('');const form=new FormData(event.currentTarget);try{const session=await repository().login(String(form.get('login')),String(form.get('password')));onLogin(session,form.get('remember')==='on');}catch(reason){setError(reason instanceof Error?reason.message:'Не удалось войти');}finally{setBusy(false);}}}>
          <label>Логин, почта или телефон<div className="input-icon"><UserRound size={19}/><input name="login" autoComplete="username" placeholder="Логин, почта или +7 999 000-00-00" required/></div></label>
          <label>Пароль<div className="input-icon"><LockKeyhole size={19}/><input name="password" type={show?'text':'password'} autoComplete="current-password" placeholder="Введите пароль" required/><button type="button" className="icon-button" onClick={()=>setShow(!show)} aria-label={show?'Скрыть пароль':'Показать пароль'}>{show?<Eye size={19}/>:<EyeOff size={19}/>}</button></div></label>
          <div className="login-options"><label className="check-label"><input type="checkbox" name="remember"/>Запомнить меня</label><button type="button" className="text-button" onClick={()=>setHelp(!help)} aria-expanded={help}>Забыли пароль?</button></div>
          {error&&<div className="form-error" role="alert">{error}</div>}{help&&<div className="info-note">Для восстановления пароля обратитесь к администратору.</div>}
          <button className="primary login-submit" disabled={busy}>{busy?<LoaderCircle className="spin" size={20}/>:<>Продолжить<ArrowRight size={20}/></>}</button>
        </form>
      </div>
      <SiteFooter/>
    </section>
  </main>;
}
