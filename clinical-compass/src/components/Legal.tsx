'use client';

import { useEffect, useState } from 'react';
import { Cookie, X } from 'lucide-react';
import Link from 'next/link';

const COOKIE_NOTICE_KEY = 'clinical-compass-cookie-notice';

export function LegalLinks(){
  return <nav className="legal-links" aria-label="Правовая информация">
    <Link href="/terms/">Правила использования</Link>
    <Link href="/privacy/">Персональные данные и конфиденциальность</Link>
    <Link href="/consent/">Согласие на обработку данных</Link>
    <Link href="/cookies/">Файлы cookie</Link>
  </nav>;
}

export function CookieNotice(){
  const [visible,setVisible]=useState(false);
  useEffect(()=>{setVisible(localStorage.getItem(COOKIE_NOTICE_KEY)!=='acknowledged');},[]);
  if(!visible)return null;
  function close(){localStorage.setItem(COOKIE_NOTICE_KEY,'acknowledged');setVisible(false);}
  return <aside className="cookie-notice" aria-label="Уведомление об использовании файлов cookie">
    <Cookie size={22}/><div><strong>На сайте используются необходимые cookie</strong><p>Они поддерживают вход в аккаунт и безопасность сессии. Дополнительные аналитические и рекламные cookie сейчас не используются.</p><Link href="/cookies/">Подробнее о cookie</Link></div>
    <button className="cookie-accept" onClick={close}>Понятно</button><button className="cookie-close" onClick={close} aria-label="Закрыть уведомление"><X size={18}/></button>
  </aside>;
}
