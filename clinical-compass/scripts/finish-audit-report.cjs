const fs=require('fs');
const rows=[['Вход, мобильный','mobile'],['Вход, компьютер','desktop'],['Конфиденциальность, компьютер','privacy']].map(([label,name])=>{
 const a=JSON.parse(fs.readFileSync(`audit-results/lighthouse-${name}.report.json`,'utf8'));
 const c=a.categories;
 return `| ${label} | ${Math.round(c.performance.score*100)} | ${Math.round(c.accessibility.score*100)} | ${Math.round(c['best-practices'].score*100)} | ${Math.round(c.seo.score*100)} | ${a.audits['largest-contentful-paint'].displayValue} | ${a.audits['cumulative-layout-shift'].displayValue} |`;
});
const table='| Страница | Performance | Accessibility | Best Practices | SEO | LCP | CLS |\n|---|---:|---:|---:|---:|---:|---:|\n'+rows.join('\n');
let report=fs.readFileSync('../docs/SITE_AUDIT_REPORT.md','utf8');
report=report.replace('<!-- LIGHTHOUSE_RESULTS -->',table+'\n\nВ мобильных прогонах результат менялся с нагрузкой на компьютер; оценка не гарантирует такую же скорость в реальной мобильной сети. Размер начального JavaScript уменьшен, дальнейшая оптимизация гидратации и анимации остаётся возможным улучшением.');
fs.writeFileSync('../docs/SITE_AUDIT_REPORT.md',report);
console.log(table);
