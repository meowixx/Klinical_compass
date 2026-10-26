"use client";
import { useEffect, useState } from "react";
import type { MedicationReview } from "@/types";
import { repository, formatDate } from "@/services";

export function MedicationReviewForm({ patientId }: { patientId: string }) {
  const [review, setReview] = useState<MedicationReview | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    repository().getMedicationReview(patientId).then(value => { if (active) setReview(value); })
      .catch(() => { if (active) setError("Не удалось загрузить проверку. Обновите страницу."); });
    return () => { active = false; };
  }, [patientId]);
  function update(patch: Partial<MedicationReview>) {
    setReview(value => value ? { ...value, ...patch } : value);
    setSaved(false);
  }
  async function save() {
    if (!review || !window.confirm("Сохранить результаты проверки врачом для выбранного пациента?")) return;
    setBusy(true); setError("");
    try { setReview(await repository().saveMedicationReview(patientId, review)); setSaved(true); }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось сохранить проверку."); }
    finally { setBusy(false); }
  }
  return <details className="medication-review">
    <summary>Проверка врачом перед лекарственным предложением</summary>
    <p>Заполните после проверки анамнеза, актуальной инструкции и взаимодействий. Без подтверждения сведения считаются неизвестными.</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    {!review && !error && <p role="status">Загрузка проверки…</p>}
    {review && <fieldset disabled={busy} className="form-stack">
      <legend className="field-heading">Подтверждённые сведения</legend>
      <label className="check-label"><input type="checkbox" checked={review.diagnosisConfirmed} onChange={e => update({ diagnosisConfirmed: e.target.checked })} /><span>Диагноз подтверждён врачом</span></label>
      <label className="check-label"><input type="checkbox" checked={review.firstTwoLinesRefractory} onChange={e => update({ firstTwoLinesRefractory: e.target.checked })} /><span>Проверена неэффективность двух предыдущих линий лечения, их достаточность и соблюдение</span></label>
      <label className="check-label"><input type="checkbox" checked={review.contraindicationsReviewed} onChange={e => update({ contraindicationsReviewed: e.target.checked })} /><span>Проверены противопоказания, аллергии, взаимодействия, беременность и кормление, функция почек и печени</span></label>
      <label>Выявленные ограничения<textarea rows={3} value={review.restrictions} maxLength={2000} onChange={e => update({ restrictions: e.target.value })} placeholder="Каждое ограничение с новой строки. Оставьте пустым, только если ограничений не выявлено." /></label>
      <div className="ai-actions"><button type="button" className="outline" onClick={save}>{busy ? "Сохранение…" : "Сохранить проверку"}</button></div>
      <p role="status">{saved ? "Проверка сохранена. Теперь можно сформировать новый черновик." : review.reviewedAt ? `Последняя проверка: ${formatDate(review.reviewedAt, true)}` : "Проверка противопоказаний ещё не подтверждена."}</p>
    </fieldset>}
  </details>;
}
