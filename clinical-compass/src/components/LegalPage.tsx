import { ArrowLeft, ShieldCheck } from 'lucide-react';
import Link from 'next/link';
import { LegalLinks } from './Legal';
import { Logo } from './ui';
import { legalDetails, legalDetailsComplete } from '@/lib/legal';

export function LegalPage({title,updated='20 октября 2026',children}:{title:string;updated?:string;children:React.ReactNode}){
  return <main className="legal-page"><header className="legal-header"><Link href="/" aria-label="Клинический компас — на главную"><Logo/></Link><Link className="legal-back" href="/"><ArrowLeft size={17}/>На главную</Link></header><article className="legal-document">
    <div className="legal-title"><ShieldCheck size={30}/><div><h1>{title}</h1><p>Редакция от {updated}</p></div></div>
    {!legalDetailsComplete&&<div className="legal-config-warning" role="note"><strong>Перед публикацией заполните реквизиты оператора.</strong> Укажите адрес и контакт для обращений в переменных окружения сайта.</div>}
    <section className="legal-operator"><h2>Оператор персональных данных</h2><dl><div><dt>Оператор</dt><dd>{legalDetails.operator}</dd></div><div><dt>Адрес</dt><dd>{legalDetails.address}</dd></div><div><dt>Обращения по персональным данным</dt><dd>{legalDetails.email}</dd></div>{legalDetails.registry&&<div><dt>Регистрационные сведения</dt><dd>{legalDetails.registry}</dd></div>}</dl></section>
    {children}
  </article><footer className="legal-page-footer"><LegalLinks/><p>© {new Date().getFullYear()} Клинический компас</p></footer></main>;
}
