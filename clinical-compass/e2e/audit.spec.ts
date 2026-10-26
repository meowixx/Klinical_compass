import { test, expect, Page } from '@playwright/test';
import fs from 'node:fs';
import AxeBuilder from '@axe-core/playwright';

export async function login(page: Page, role = 'doctor') {
  const accounts = { doctor: ['Persent','Admin321'], patient: ['Doctor','Admin241'], admin: ['Admin','AdminAIMPY'] };
  await page.goto('/');
  const cookie = page.getByRole('button', { name: 'Понятно', exact: true });
  if (await cookie.isVisible()) await cookie.click();
  const [name,password] = accounts[role as keyof typeof accounts];
  await page.locator('input[name=login]').fill(name);
  await page.locator('input[name=password]').fill(password);
  await page.getByRole('button', { name: 'Продолжить', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Выйти', exact: true })).toBeVisible();
  await expect(page.getByText('Загружаем рабочий кабинет', { exact: true })).toHaveCount(0);
}

test('all roles, pages, responsive layout and console baseline', async ({ browser }) => {
  test.setTimeout(180000);
  const findings: {role:string;label?:string;width?:number;content?:number;errors?:string[];accessibility?:unknown[];offenders?:string[]}[] = [];
  fs.mkdirSync('audit-results/screenshots', { recursive: true });
  for (const role of ['login','doctor','patient','admin']) {
    const context = await browser.newContext({ reducedMotion: 'reduce' });
    const page = await context.newPage();
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('response', r => { if (r.status() >= 500) errors.push(`${r.status()} ${r.url()}`); });
    if (role === 'login') await page.goto('/'); else await login(page, role);
    const labels = role==='doctor' ? ['Обзор','Пациенты','Уведомления','Задания','Сообщения','ИИ-помощник','База знаний','Отчёты','Настройки']
      : role==='admin' ? ['Обзор системы','Backend и API','Проверка функций','Данные и показатели','Библиотека опросников','Учётные записи','Журнал аудита','Настройки']
      : role==='patient' ? ['Главная','История наблюдения','Назначения','Опросники','Документы','Профиль'] : ['login'];
    for (const label of labels) {
      await page.setViewportSize({ width: 1440, height: 1000 });
      if (role !== 'login') await page.getByRole('button', { name: new RegExp('^'+label) }).first().click();
      await page.waitForTimeout(350);
      for (const width of [320,375,390,768,1024,1440,1920]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate(()=>new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve()))));
        const overflow = await page.evaluate(() => ({
          width: innerWidth, content: document.documentElement.scrollWidth,
          offenders: [...document.querySelectorAll('main *, .role-content *, .login-page *')].filter(e => {
            const r=e.getBoundingClientRect(); return r.width > 0 && r.right > innerWidth+2 && getComputedStyle(e).position!=='absolute';
          }).slice(0,8).map(e=>`${e.tagName}.${e.className}`),
        }));
        findings.push({role,label,...overflow});
        if ([320,390,1440].includes(width)) await page.screenshot({ path: `audit-results/screenshots/${role}-${labels.indexOf(label)}-${width}.png`, fullPage: true });
      }
      if (['login','Сообщения','Профиль','Учётные записи'].includes(label)) {
        const axe=await new AxeBuilder({page}).analyze();
        findings.push({role,label,accessibility:axe.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}))});
      }
    }
    findings.push({role,errors});
    await context.close();
  }
  fs.writeFileSync('audit-results/browser-scan.json', JSON.stringify(findings,null,2));
  expect(findings.filter(item=>(item.content||0)>(item.width||0)+1 || item.errors?.length || item.accessibility?.length)).toEqual([]);
});
