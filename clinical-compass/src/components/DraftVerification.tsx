"use client";
import { AlertTriangle, CircleCheck, CircleHelp, Pill, UserRound } from "lucide-react";
import type { AiVerification, DrugExcerpt, GuidelineCitation, MedicationCheck } from "@/types";
import { InfoNote, SourceLink } from "./ui";

const registryLabels: Record<MedicationCheck["registry"]["status"], string> = {
  active: "Зарегистрирован в ГРЛС",
  expired: "Регистрация в ГРЛС истекла",
  not_found: "Не найден в ГРЛС",
};

function CitationQuote({ item }: { item: GuidelineCitation | DrugExcerpt }) {
  return (
    <figure className="kb-quote">
      <blockquote>{item.quote}</blockquote>
      <figcaption>
        <SourceLink url={item.url}>
          {item.title}, стр. {item.page}
        </SourceLink>
        {item.recommendationLevel && (
          <span className="kb-tag">Уровень убедительности {item.recommendationLevel}</span>
        )}
        {"offLabel" in item && item.offLabel && (
          <span className="kb-tag warn">Вне инструкции (#)</span>
        )}
        {"appliesTo" in item && item.appliesTo.startsWith("класс") && (
          <span className="kb-tag">Относится к: {item.appliesTo}</span>
        )}
      </figcaption>
    </figure>
  );
}

function MedicationCard({ medication }: { medication: MedicationCheck }) {
  const { registry } = medication;
  return (
    <section className="kb-medication" aria-label={`Проверка препарата ${medication.name}`}>
      <header>
        <Pill size={18} />
        <strong>{medication.name}</strong>
        {medication.drugClass && <span className="kb-tag">{medication.drugClass}</span>}
        <span className={`kb-status ${registry.status}`}>{registryLabels[registry.status]}</span>
      </header>
      {medication.patientConflicts.length > 0 && (
        <ul className="kb-conflicts">
          {medication.patientConflicts.map((conflict) => (
            <li key={conflict}>
              <UserRound size={15} />
              {conflict}
            </li>
          ))}
        </ul>
      )}
      <h5>Государственный реестр лекарственных средств</h5>
      {registry.entries.length ? (
        <>
          <ul className="kb-registry">
            {registry.entries.map((entry) => (
              <li key={entry.registrationNumber + entry.tradeName} className={entry.active ? "" : "inactive"}>
                <span>{entry.tradeName}</span>
                <code>{entry.registrationNumber}</code>
                <small>до {entry.validUntil}</small>
              </li>
            ))}
          </ul>
          {registry.totalCount > registry.entries.length && (
            <small className="kb-muted">
              Показано {registry.entries.length} из {registry.totalCount} записей, действующих: {registry.activeCount}.
            </small>
          )}
        </>
      ) : (
        <p className="kb-muted">Записей с таким наименованием в выгрузке ГРЛС нет.</p>
      )}
      <SourceLink url={registry.searchUrl}>Открыть ГРЛС: поиск по номеру удостоверения</SourceLink>
      <h5>Дозировка по клиническим рекомендациям Минздрава</h5>
      {medication.dosing.length ? (
        medication.dosing.map((item) => <CitationQuote item={item} key={item.url + item.quote} />)
      ) : (
        <p className="kb-muted">В базе клинических рекомендаций доза не найдена. Сверьте с инструкцией в ГРЛС.</p>
      )}
      <h5>Противопоказания и предостережения</h5>
      {medication.contraindications.length ? (
        medication.contraindications.map((item) => <CitationQuote item={item} key={item.url + item.quote} />)
      ) : (
        <p className="kb-muted">В клинических рекомендациях базы противопоказания для препарата не найдены.</p>
      )}
      <p className="kb-muted">
        Полный перечень противопоказаний, форм выпуска и дозировок приведён в инструкции по применению. Откройте её в ГРЛС
        по номеру регистрационного удостоверения перед назначением.
      </p>
    </section>
  );
}

export function DraftVerification({ verification, edited }: { verification?: AiVerification | null; edited: boolean }) {
  if (!verification) {
    return <InfoNote>Проверка по клиническим рекомендациям и ГРЛС для этого ответа недоступна.</InfoNote>;
  }
  const statementIcons = {
    supported: <CircleCheck size={16} />,
    patient_data: <UserRound size={16} />,
    unverified: <CircleHelp size={16} />,
  };
  const statementLabels = {
    supported: "Подтверждено КР",
    patient_data: "Данные пациента",
    unverified: "Нет подтверждения в КР",
  };
  return (
    <section className="kb-check" aria-label="Проверка ответа по базе знаний">
      <h4>Проверка по клиническим рекомендациям и ГРЛС</h4>
      {edited && (
        <p className="kb-edited">
          Проверка относится к сохранённому тексту. Сохраните правки, чтобы проверить ответ заново.
        </p>
      )}
      {verification.guideline && (
        <p className="kb-muted">
          Рекомендации по диагнозу пациента:{" "}
          <SourceLink url={verification.guideline.url}>{verification.guideline.title}</SourceLink>
        </p>
      )}
      {verification.warnings.length > 0 && (
        <ul className="kb-warnings">
          {verification.warnings.map((warning) => (
            <li key={warning}>
              <AlertTriangle size={15} />
              {warning}
            </li>
          ))}
        </ul>
      )}
      {verification.medications.map((medication) => (
        <MedicationCard medication={medication} key={medication.name} />
      ))}
      {verification.statements.length > 0 && (
        <>
          <h5>Проверка утверждений ответа</h5>
          <ul className="kb-statements">
            {verification.statements.map((statement, index) => (
              <li key={index} className={statement.status}>
                {statementIcons[statement.status]}
                <div>
                  <span>{statement.text}</span>
                  <small>
                    {statementLabels[statement.status]}
                    {statement.citation && (
                      <>
                        {" · "}
                        <SourceLink url={statement.citation.url}>
                          {statement.citation.title}, стр. {statement.citation.page}
                        </SourceLink>
                      </>
                    )}
                  </small>
                  {statement.citation && <blockquote>{statement.citation.quote}</blockquote>}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="kb-muted">{verification.limitations}</p>
    </section>
  );
}
