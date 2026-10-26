import { z } from 'zod';
import type { AlertUpdate, ClinicalAlert } from '../types';
export const patientSchema = z.object({name:z.string().trim().min(2,'Введите имя, минимум 2 символа').max(80),age:z.coerce.number().int().min(18,'Возраст должен быть не менее 18 лет').max(120),sex:z.enum(['Ж','М']),code:z.enum(['F32.0','F41.1'])});
export function validateAlertUpdate(alert: ClinicalAlert, update: AlertUpdate) {
 if (update.status==='closed' && alert.level==='red' && update.comment.trim().length<5) throw new Error('Для закрытия критического алерта нужен комментарий врача (минимум 5 символов).');
 if (update.status==='closed' && !update.action.trim()) throw new Error('Укажите выполненное действие.');
}

