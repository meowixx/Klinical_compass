import type { Metadata } from 'next';
import '@fontsource-variable/manrope';
import './globals.css';
import { CookieNotice } from '@/components/Legal';
export const metadata: Metadata = { title: 'Клинический компас — кабинет врача', description: 'Цифровой ассистент врача для наблюдения пациентов между визитами.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="ru"><body>{children}<CookieNotice/></body></html>; }
