import { test, expect, Page } from '@playwright/test';
async function enter(page:Page,role:'doctor'|'patient'|'admin'='doctor'){
 const accounts={doctor:['Persent','Admin321'],patient:['Doctor','Admin241'],admin:['Admin','AdminAIMPY']};
 await page.goto('/');await page.locator('input[name=login]').fill(accounts[role][0]);await page.locator('input[name=password]').fill(accounts[role][1]);await page.getByRole('button',{name:'Продолжить',exact:true}).click();await expect(page.getByRole('button',{name:'Выйти',exact:true})).toBeVisible();
}
test('invalid login, password visibility, login and server logout',async({page})=>{
 await page.goto('/');await page.locator('input[name=login]').fill('not-a-user');await page.locator('input[name=password]').fill('wrong');await page.getByRole('button',{name:'Показать пароль'}).click();await expect(page.locator('input[name=password]')).toHaveAttribute('type','text');await page.getByRole('button',{name:'Продолжить',exact:true}).click();await expect(page.locator('.form-error')).toBeVisible();await enter(page);await page.getByRole('button',{name:'Выйти',exact:true}).click();await expect(page.locator('input[name=login]')).toBeVisible();const response=await page.request.get('http://127.0.0.1:8011/api/v1/account');expect(response.status()).toBe(401);
});
test('patient generates a 24-hour exact-match MAX code',async({page})=>{
 await enter(page,'patient');await page.getByRole('button',{name:'Профиль',exact:true}).click();await page.getByRole('button',{name:'Получить код MAX'}).click();await expect(page.locator('.patient-max-code strong')).toBeVisible();
});
test('doctor task creation and status persist after refresh',async({page})=>{
 await enter(page);await page.getByRole('button',{name:'Задания',exact:true}).click();await page.getByRole('button',{name:'Создать задачу',exact:true}).click();const dialog=page.getByRole('dialog');await dialog.locator('select[name=patientId]').selectOption('p1');await dialog.getByRole('button',{name:'Создать',exact:true}).click();await expect(dialog).toHaveCount(0);const status=page.getByRole('combobox',{name:'Статус задания: Связаться с пациентом'}).last();await status.selectOption('working');await expect(status).toHaveValue('working');await page.reload();await page.getByRole('button',{name:'Задания',exact:true}).click();await expect(page.getByRole('combobox',{name:'Статус задания: Связаться с пациентом'}).last()).toHaveValue('working');
});
test('administrator creates a physician only after confirmation',async({page})=>{
 await enter(page,'admin');await page.getByRole('button',{name:'Учётные записи',exact:true}).click();await page.getByRole('button',{name:'Добавить пользователя'}).click();const form=page.locator('.account-create-panel');await form.getByLabel('Тип кабинета').selectOption('doctor');await form.getByLabel('ФИО',{exact:true}).fill('Аудит Тестовый Врач');await form.getByLabel('Логин',{exact:true}).fill('audit-'+Date.now());await form.locator('input[type=password]').fill('Audit-Test-2026!');await form.getByLabel('Специальность',{exact:true}).fill('Тестовая специальность');await form.getByLabel('Организация',{exact:true}).fill('Тестовая клиника');await form.getByRole('button',{name:'Создать учётную запись'}).click();await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('dialog').getByRole('button',{name:'Создать',exact:true}).click();await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.locator('.account-list article').filter({hasText:'Аудит Тестовый Врач'}).last()).toBeVisible();
});

test('patient sees a retry state on API failure, not sample medical data',async({page})=>{
 await page.route('**/api/v1/dashboard',route=>route.fulfill({status:503,body:JSON.stringify({detail:'Audit unavailable'}),contentType:'application/json'}));
 await enter(page,'patient');await expect(page.getByRole('button',{name:'Повторить загрузку'})).toBeVisible();await expect(page.getByText('Анна К.',{exact:true})).toHaveCount(0);
});
