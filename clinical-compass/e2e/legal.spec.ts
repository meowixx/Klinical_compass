import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
test('legal routes and navigation are readable on mobile',async({page})=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
 for(const route of ['terms','privacy','consent','cookies']){
  await page.setViewportSize({width:320,height:900});const response=await page.goto('/'+route+'/');expect(response?.status()).toBe(200);await expect(page.locator('h1')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(321);
  await page.screenshot({path:`audit-results/screenshots/legal-${route}-320.png`,fullPage:true});
 }
 await page.setViewportSize({width:1440,height:1000});await page.goto('/privacy/');const axe=await new AxeBuilder({page}).analyze();expect(axe.violations.map(item=>item.id)).toEqual([]);
 expect(errors).toEqual([]);
});
