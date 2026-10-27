"use client";
import { useEffect, useState } from "react";
import {
  Activity,
  Bell,
  BookOpen,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  Copy,
  Database,
  FileCheck2,
  HeartPulse,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  LoaderCircle,
  LogOut,
  Pill,
  Play,
  RefreshCw,
  Server,
  Settings,
  ShieldCheck,
  UserRound,
  UsersRound,
} from "lucide-react";
import type { AppData, MaxLinkCode } from "@/types";
import { createSeed } from "@/mock/seed";
import { DynamicsChart } from "./Chart";
import { Avatar, Badge, SiteFooter, Empty, InfoNote, Logo } from "./ui";
import { isMock } from "@/services";
import { QuestionnaireLibraryAdmin } from "./QuestionnaireLibraryAdmin";
import { AdminAccounts } from "./AdminAccounts";

type AdminPage =
  | "overview"
  | "health"
  | "functions"
  | "data"
  | "library"
  | "accounts"
  | "audit"
  | "settings";
const adminNav: [AdminPage, string, typeof LayoutDashboard][] = [
  ["overview", "Обзор системы", LayoutDashboard],
  ["health", "Backend и API", Server],
  ["functions", "Проверка функций", ListChecks],
  ["data", "Данные и показатели", Database],
  ["library", "Библиотека опросников", BookOpen],
  ["accounts", "Учётные записи", UsersRound],
  ["audit", "Журнал аудита", ShieldCheck],
  ["settings", "Настройки", Settings],
];
/* eslint-disable @typescript-eslint/no-unused-vars -- compact JSX maps include an index in the endpoint status renderer */
export function AdminPortal({ onLogout }: { onLogout: () => void }) {
  const [data, setData] = useState<AppData>(createSeed());
  const [dataReady,setDataReady]=useState(false);
  const [loadError,setLoadError]=useState('');
  const [page, setPage] = useState<AdminPage>("overview");
  const [running, setRunning] = useState(false);
  const [checked, setChecked] = useState(false);
  const [connection,setConnection]=useState(false);
  const [toast, setToast] = useState("");
  function notify(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 3200);
  }
  useEffect(() => {
    import("@/services")
      .then(({ repository }) => repository().getData())
      .then(value=>{setData(value);setDataReady(true);})
      .catch((reason) =>
        setLoadError(
          reason instanceof Error
            ? reason.message
            : "Не удалось загрузить данные",
        ),
      );
  }, []);
  async function runChecks() {
    setRunning(true);
    setChecked(false);
    try {
      const base=(process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000/api/v1').replace(/\/api\/v1\/?$/,'');
      const responses=await Promise.all(['/health','/health/db'].map(path=>fetch(base+path,{signal:AbortSignal.timeout(8000)})));
      if(responses.some(response=>!response.ok))throw new Error('Сервер или база данных недоступны');
      setConnection(true);setChecked(true);notify('Соединение с FastAPI и SQLite подтверждено.');
    }catch{setConnection(false);notify('Не удалось подтвердить соединение с FastAPI и SQLite.');}finally{setRunning(false);}
  }

  if(!dataReady)return <div className="state-page" role="status">{loadError||'Загрузка данных…'}{loadError&&<button className="outline" onClick={()=>window.location.reload()}>Повторить загрузку</button>}<button className="text-button" onClick={onLogout}>Выйти</button></div>;
  const critical = data.alerts.filter(
    (a) => a.level === "red" && a.status !== "closed",
  ).length;
  return (
    <PortalFrame
      title="Кабинет администратора"
      subtitle="Контроль системы и готовности backend"
      nav={adminNav}
      page={page}
      setPage={setPage}
      onLogout={onLogout}
      initials="АД"
    >
      <div className="role-page-heading">
        <div>
          <h1>{adminNav.find((n) => n[0] === page)?.[1]}</h1>
          <p>
            {isMock
              ? "Локальное хранилище подключено."
              : connection ? "FastAPI и база данных доступны." : "Проверьте соединение с сервером."}
          </p>
        </div>
        <button className="primary" onClick={runChecks} disabled={running}>
          {running ? (
            <LoaderCircle className="spin" size={18} />
          ) : (
            <Play size={18} />
          )}
          Проверить соединение
        </button>
      </div>
      {page === "library" && <QuestionnaireLibraryAdmin notify={notify} />}{" "}
      {page === "overview" && (
        <>
          <div className="admin-kpis">
            <Kpi
              icon={UsersRound}
              value={data.patients.length}
              label="Пациентов"
              tone="blue"
            />
            <Kpi
              icon={Bell}
              value={critical}
              label="Критических сигналов"
              tone="red"
            />
            <Kpi
              icon={ClipboardCheck}
              value={data.tasks.length}
              label="Заданий в системе"
              tone="violet"
            />
            <Kpi
              icon={Activity}
              value={connection ? "Доступен" : "Не проверен"}
              label="Состояние сервера"
              tone="green"
            />
          </div>
          <div className="admin-grid">
            <section className="card">
              <div className="section-heading">
                <div>
                  <h2>Состояние компонентов</h2>
                  <p>Последняя локальная проверка: сейчас</p>
                </div>
                <Badge risk="green" text="Frontend работает" />
              </div>
              <HealthRows api={false} connected={connection} />
            </section>
            <section className="card admin-summary">
              <h2>Контрольные показатели</h2>
              <Metric
                label="Приверженность, среднее"
                value={`${Math.round(data.patients.reduce((s, p) => s + p.adherence, 0) / Math.max(1, data.patients.length))}%`}
                progress={Math.round(data.patients.reduce((s,p)=>s+p.adherence,0)/Math.max(1,data.patients.length))}
              />
              <Metric
                label="Обработано сигналов"
                value={`${data.alerts.filter((a) => a.status === "closed").length}/${data.alerts.length}`}
                progress={
                  data.alerts.length
                    ? (data.alerts.filter((a) => a.status === "closed").length /
                        data.alerts.length) *
                      100
                    : 0
                }
              />
              
              <InfoNote>
                Показатели рассчитаны по текущим данным системы.
              </InfoNote>
            </section>
          </div>
          <section className="card">
            <div className="section-heading">
              <h2>Последние системные события</h2>
              <button className="text-button" onClick={() => setPage("audit")}>
                Весь журнал
                <ChevronRight size={16} />
              </button>
            </div>
            <SystemEvents data={data} />
          </section>
        </>
      )}
      {page === "health" && (
        <>
          <div className="admin-grid">
            <section className="card">
              <h2>Backend и хранилище</h2>
              <HealthRows api connected={connection} />
              <InfoNote>
                {isMock
                  ? "Эта сборка использует MockClinicalRepository. Для API задайте NEXT_PUBLIC_DATA_SOURCE=api."
                  : "Данные загружаются через FastAPI; состояние хранилища проверяется сервером."}
              </InfoNote>
            </section>
            <section className="card">
              <h2>Конфигурация</h2>
              <CodeLine
                label="Источник данных"
                value={isMock ? "mock" : "FastAPI"}
              />
              <CodeLine
                label="API"
                value={
                  process.env.NEXT_PUBLIC_API_URL ||
                  "http://localhost:8000/api/v1"
                }
              />
              <CodeLine
                label="Сессия"
                value={isMock ? "браузерная сессия" : "HttpOnly cookie"}
              />
              <CodeLine
                label="Хранилище"
                value={isMock ? "localStorage" : "SQLite"}
              />
            </section>
          </div>
          <section className="card">
            <h2>Контракт API</h2>
            <div className="endpoint-grid">
              {[
                "POST /auth/login",
                "GET /doctor/dashboard",
                "GET /patients",
                "POST /patients",
                "GET /alerts",
                "PATCH /alerts/{id}",
                "POST /ai/summary",
                "GET /audit",
              ].map((x, i) => (
                <div key={x}>
                  <span
                    className="status-dot planned"
                  />
                  <code>{x}</code>
                  <small>
                    {isMock
                      ? i < 1
                        ? "Эмулируется"
                        : "Готов в API"
                      : "В контракте"}
                  </small>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
      {page === "functions" && (
        <section className="card">
          <div className="section-heading">
            <div>
              <h2>Матрица функций</h2>
              <p>Проверка основных пользовательских сценариев</p>
            </div>
            {checked && <Badge risk="green" text="Соединение проверено" />}
          </div>
          <div className="function-grid">
            {[
              ["Авторизация по трём ролям", "Администратор, врач, пациент"],
              ["Карточка пациента", "Вкладки, графики и документы"],
              ["Критический сигнал", "Комментарий обязателен при закрытии"],
              ["ИИ-консилиум", "Локальный консультационный ответ"],
              ["Mock-репозиторий", "Чтение и запись localStorage"],
              ["Формы", "Валидация пациента и задач"],
              ["Адаптивность", "Ноутбук и планшет"],
              ["Экспорт отчёта", "Имитация без создания файла"],
            ].map(([name, desc], i) => (
              <article key={name}>
                <span className="check-idle">
                  <Clock3 size={17} />
                </span>
                <div>
                  <strong>{name}</strong>
                  <p>{desc}</p>
                </div>
                <span className="badge green">
                  Требует проверки
                </span>
              </article>
            ))}
          </div>
        </section>
      )}
      {page === "data" && (
        <>
          <div className="admin-kpis">
            <Kpi
              icon={Database}
              value={data.patients.length}
              label="Пациентов"
              tone="blue"
            />
            <Kpi
              icon={FileCheck2}
              value={data.assignments.length}
              label="Назначений опросников"
              tone="green"
            />
            <Kpi
              icon={Bell}
              value={data.alerts.length}
              label="Всего сигналов"
              tone="red"
            />
            <Kpi
              icon={BookOpen}
              value={data.documents.length}
              label="Карточек источников"
              tone="violet"
            />
          </div>
          <section className="card">
            <div className="section-heading">
              <div>
                <h2>Распределение риска</h2>
                <p>Сводка по текущим пациентам</p>
              </div>
              <strong>{data.patients.length} всего</strong>
            </div>
            <div
              className="risk-summary-bar"
              aria-label="Распределение пациентов по уровням риска"
            >
              {(["red", "yellow", "green"] as const).map((r) => (
                <span
                  className={r}
                  key={r}
                  style={{
                    flex: data.patients.filter((p) => p.risk === r).length,
                  }}
                />
              ))}
            </div>
            <div className="risk-summary-legend">
              {(["red", "yellow", "green"] as const).map((r) => (
                <div key={r}>
                  <Badge
                    risk={r}
                    text={
                      r === "red"
                        ? "Нужны действия"
                        : r === "yellow"
                          ? "Требуют внимания"
                          : "По плану"
                    }
                  />
                  <strong>
                    {data.patients.filter((p) => p.risk === r).length}
                  </strong>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
      {page === "accounts" && <AdminAccounts notify={notify} />}
      {page === "audit" && (
        <section className="card">
          <h2>Журнал аудита</h2>
          {data.audit.length ? (
            <SystemEvents data={data} />
          ) : (
            <Empty
              title="Действий пока нет"
              text="Закройте сигнал или измените данные в кабинете врача — событие появится здесь."
            />
          )}
        </section>
      )}
      {page === "settings" && (
        <section className="card">
          <h2>Настройки администратора</h2>
          <InfoNote>
            Администраторский кабинет показывает техническое состояние
            подключённых компонентов.
          </InfoNote>
          <div className="setting-line">
            <div>
              <strong>Режим данных</strong>
              <p>Локальное хранилище</p>
            </div>
            <span className="badge green">mock</span>
          </div>
          <div className="setting-line">
            <div>
              <strong>Журналирование</strong>
              <p>Действия сохраняются в браузере</p>
            </div>
            <span className="badge green">Включено</span>
          </div>
          <button
            className="outline"
            onClick={() => notify("Уведомление администратора показано")}
          >
            <Bell size={17} />
            Проверить уведомление
          </button>
        </section>
      )}
      {toast && <div className="toast">{toast}</div>}
    </PortalFrame>
  );
}

type PatientPage =
  "home" | "diary" | "therapy" | "tasks" | "documents" | "profile";
const patientNav: [PatientPage, string, typeof LayoutDashboard][] = [
  ["home", "Главная", LayoutDashboard],
  ["diary", "Дневник состояния", HeartPulse],
  ["therapy", "Приём препаратов", Pill],
  ["tasks", "Задания", ListChecks],
  ["documents", "Документы", FileCheck2],
  ["profile", "Профиль", UserRound],
];
export function PatientPortal({ onLogout }: { onLogout: () => void }) {
  const [data, setData] = useState<AppData>(createSeed());
  const [dataReady,setDataReady]=useState(false);
  const [loadError,setLoadError]=useState('');
  const [page, setPage] = useState<PatientPage>("home");
  const [toast, setToast] = useState("");
  const [checkin, setCheckin] = useState({
    wellbeing: 0,
    anxiety: 0,
    sleep: 7,
    note: "",
  });
  const [taken, setTaken] = useState(false);
  useEffect(() => {
    import("@/services")
      .then(({ repository }) => repository().getData())
      .then(value=>{setData(value);setDataReady(true);}).catch(()=>setLoadError('Не удалось загрузить данные. Проверьте подключение к серверу.'));
  }, []);
  if(!dataReady)return <div className="state-page" role="status">{loadError||'Загрузка данных…'}{loadError&&<button className="outline" onClick={()=>window.location.reload()}>Повторить загрузку</button>}<button className="text-button" onClick={onLogout}>Выйти</button></div>;
  const patient = data.patients[0];
  if (!patient) return <div className="splash">Данные пациента не найдены</div>;
  function notify(text: string) {
    setToast(text);
    setTimeout(() => setToast(""), 3500);
  }
  return (
    <PortalFrame
      title="Кабинет пациента"
      subtitle="Ваши данные между визитами"
      nav={patientNav}
      page={page}
      setPage={setPage}
      onLogout={onLogout}
      initials="АК"
      showRoleLabel={false}
    >
      <div className="patient-welcome">
        <div>
          <span className="eyebrow">КАБИНЕТ ПАЦИЕНТА</span>
          <h1>
            {page === "home"
              ? `Здравствуйте, ${patient.name}`
              : patientNav.find((n) => n[0] === page)?.[1]}
          </h1>
          <p>
            {page === "home"
              ? "Бот ежедневно спросит о самочувствии и задаст вопросы, выбранные врачом."
              : "Личные данные пациента"}
          </p>
        </div>
        {page === "home" && (
          <button className="primary" onClick={() => setPage("diary")}>
            <HeartPulse size={18} />
            Заполнить дневник
          </button>
        )}
      </div>
      {page === "home" && (
        <>
          <div className="patient-kpis">
            <Kpi
              icon={HeartPulse}
              value={formatSignedState(patient.dynamics.at(-1)?.wellbeing)}
              label="Состояние · шкала −10…+10"
              tone="blue"
            />
            <Kpi
              icon={Clock3}
              value={`${patient.dynamics.at(-1)?.sleep} ч`}
              label="Сон"
              tone="violet"
            />
            <Kpi
              icon={Pill}
              value={`${patient.adherence}%`}
              label="Приём препаратов"
              tone="green"
            />
            <Kpi
              icon={ListChecks}
              value={
                data.tasks.filter(
                  (t) => t.patientId === patient.id && t.status !== "done",
                ).length
              }
              label="Активных заданий"
              tone="red"
            />
          </div>
          <div className="patient-home-grid">
            <section className="card">
              <DynamicsChart data={patient.dynamics} compact />
            </section>
            <section className="card next-action">
              <h2>Ближайшее событие</h2>
              <span className="patient-action-icon">
                <CalendarDays size={25} />
              </span>
              <strong>Повторная консультация</strong>
              <p>16 октября, 15:00</p>
              <button className="outline" onClick={() => setPage("tasks")}>
                Все задания
                <ChevronRight size={16} />
              </button>
            </section>
          </div>
          <section className="card">
            <h2>На сегодня</h2>
            <div className="patient-today">
              <button onClick={() => setPage("diary")}>
                <HeartPulse />
                <span>
                  <strong>Ежедневный вопрос бота</strong>
                  <small>Состояние от −10 до +10</small>
                </span>
                <ChevronRight />
              </button>
              <button onClick={() => setPage("therapy")}>
                <Pill />
                <span>
                  <strong>Приём препаратов</strong>
                  <small>{taken ? "Выполнено" : "Ещё не отмечено"}</small>
                </span>
                <ChevronRight />
              </button>
              <button onClick={() => setPage("tasks")}>
                <ListChecks />
                <span>
                  <strong>Вопросы врача</strong>
                  <small>Бот задаст их по расписанию</small>
                </span>
                <ChevronRight />
              </button>
            </div>
          </section>
        </>
      )}
      {page === "diary" && (
        <div className="patient-home-grid">
          <section className="card diary-form">
            <h2>Ежедневный вопрос бота</h2>
            <InfoNote>
              Бот в MAX или Telegram ежедневно спросит о состоянии и задаст
              дополнительные вопросы, которые выбрал врач.
            </InfoNote>
            <Range
              label="Общее состояние"
              value={checkin.wellbeing}
              min={-10}
              max={10}
              hint="−10 — очень плохо · 0 — нейтрально · +10 — очень хорошо"
              signed
              onChange={(v) => setCheckin({ ...checkin, wellbeing: v })}
            />
            <Range
              label="Спокойствие"
              value={checkin.anxiety}
              min={-10}
              max={10}
              hint="−10 — сильная тревога · 0 — нейтрально · +10 — спокойно"
              signed
              onChange={(v) => setCheckin({ ...checkin, anxiety: v })}
            />
            <Range
              label="Сон, часов"
              value={checkin.sleep}
              min={0}
              max={12}
              hint="Укажите продолжительность сна"
              onChange={(v) => setCheckin({ ...checkin, sleep: v })}
            />
            <label>
              Комментарий
              <textarea
                value={checkin.note}
                onChange={(e) =>
                  setCheckin({ ...checkin, note: e.target.value })
                }
                rows={4}
                placeholder="Что важно сообщить врачу?"
              />
            </label>
            <button
              className="primary"
              onClick={() => notify("Дневник сохранён.")}
            >
              <Check size={18} />
              Сохранить запись
            </button>
          </section>
          <section className="card">
            <h2>Важно</h2>
            <InfoNote>Дневник не предназначен для экстренной помощи.</InfoNote>
            <p className="muted">
              При резком ухудшении состояния обратитесь за очной медицинской
              помощью по правилам вашей организации.
            </p>
          </section>
        </div>
      )}
      {page === "therapy" && (
        <section className="card">
          <h2>Приём препаратов</h2>
          <InfoNote>
            Этот раздел нужен только когда врач включил контроль приёма. Пациент
            подтверждает приём сам или отвечает на такой вопрос в боте; раздел
            не меняет назначения.
          </InfoNote>
          {patient.prescriptions.map((rx) => (
            <article className="therapy-patient-card" key={rx.id}>
              <div>
                <span className="eyebrow">НАЗНАЧЕНИЕ</span>
                <h3>{rx.medication.name}</h3>
                <p>{rx.regimen}</p>
              </div>
              <button
                className={taken ? "outline" : "primary"}
                onClick={() => {
                  setTaken(!taken);
                  notify(taken ? "Отметка снята" : "Приём отмечен локально");
                }}
              >
                {taken ? <RefreshCw size={17} /> : <Check size={17} />}{" "}
                {taken ? "Изменить отметку" : "Отметить приём"}
              </button>
            </article>
          ))}
        </section>
      )}
      {page === "tasks" && (
        <section className="card">
          <h2>Вопросы и задания врача</h2>
          <InfoNote>
            Бот покажет назначенные врачом вопросы в MAX или Telegram по
            заданному расписанию.
          </InfoNote>
          {data.tasks
            .filter((t) => t.patientId === patient.id)
            .map((t) => (
              <article className="patient-list-row" key={t.id}>
                <ListChecks />
                <div>
                  <strong>{t.title}</strong>
                  <p>
                    {new Date(t.dueAt).toLocaleString("ru-RU", {
                      day: "numeric",
                      month: "long",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                </div>
                <Badge
                  risk={t.status === "done" ? "green" : "yellow"}
                  text={t.status === "done" ? "Выполнено" : "Ожидается"}
                />
              </article>
            ))}
        </section>
      )}
      {page === "documents" && (
        <section className="card">
          <h2>Мои документы</h2>
          <Empty
            title="Документы не загружены"
            text="Загруженные документы появятся в этом разделе."
          />
        </section>
      )}
      {page === "profile" && (
        <section className="card patient-profile">
          <Avatar patient={patient} />
          <div>
            <h2>{patient.name}</h2>
            <p>Карта {patient.card}</p>
            <small>
              {patient.age} лет · лечащий врач: {patient.doctor}
            </small>
          </div>
          <InfoNote>
            Доступ к сведениям определяется ролью пользователя.
          </InfoNote>
        </section>
      )}
      {toast && <div className="toast">{toast}</div>}
    </PortalFrame>
  );
}

function PortalFrame<P extends string>({
  title,
  subtitle,
  nav,
  page,
  setPage,
  onLogout,
  initials,
  showRoleLabel = true,
  children,
}: {
  title: string;
  subtitle: string;
  nav: [P, string, typeof LayoutDashboard][];
  page: P;
  setPage: (p: P) => void;
  onLogout: () => void;
  initials: string;
  showRoleLabel?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="role-shell">
      <aside className="role-sidebar">
        <Logo />
        {showRoleLabel && (
          <div className="role-label">
            <strong>{title}</strong>
            <small>{subtitle}</small>
          </div>
        )}
        <nav>
          {nav.map(([id, label, Icon]) => (
            <button
              className={page === id ? "active" : ""}
              key={id}
              onClick={() => setPage(id)}
            >
              <Icon size={20} />
              {label}
            </button>
          ))}
        </nav>
        <div className="role-user">
          <span className="doctor-avatar">{initials}</span>
          <span>
            <strong>{title}</strong>
            <small>Авторизованный пользователь</small>
          </span>
        </div>
        <button className="role-logout" onClick={onLogout}>
          <LogOut size={19} />
          Выйти
        </button>
      </aside>
      <main className="role-content">
        {children}
        <SiteFooter />
      </main>
    </div>
  );
}
function Kpi({
  icon: Icon,
  value,
  label,
  tone,
}: {
  icon: typeof Activity;
  value: string | number;
  label: string;
  tone: string;
}) {
  return (
    <div className={`role-kpi ${tone}`}>
      <span>
        <Icon size={22} />
      </span>
      <div>
        <strong>{value}</strong>
        <small>{label}</small>
      </div>
    </div>
  );
}
function HealthRows({ api, connected }: { api: boolean; connected: boolean }) {
  const rows = [
    ["Next.js frontend", "Работает", "ok"],
    ["Ролевая авторизация", "3 роли", "ok"],
    [
      "FastAPI backend",
      connected ? "Подключён" : api ? "Не проверен" : "Ожидает проверки",
      connected ? "ok" : "wait",
    ],
    [
      "SQLite",
      connected ? "Подключена" : "Не проверена",
      connected ? "ok" : "wait",
    ],
  ];
  return (
    <div className="health-list">
      {rows.map(([name, state, status]) => (
        <div key={name}>
          <span className={`health-icon ${status}`}>
            {status === "ok" ? <CheckCircle2 /> : <Clock3 />}
          </span>
          <strong>{name}</strong>
          <small>{state}</small>
        </div>
      ))}
    </div>
  );
}
function Metric({
  label,
  value,
  progress,
}: {
  label: string;
  value: string;
  progress: number;
}) {
  return (
    <div className="admin-metric">
      <span>
        <strong>{label}</strong>
        <em>{value}</em>
      </span>
      <div>
        <i style={{ width: `${Math.min(100, progress)}%` }} />
      </div>
    </div>
  );
}
function CodeLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="code-line">
      <span>{label}</span>
      <code>{value}</code>
    </div>
  );
}
function SystemEvents({ data }: { data: AppData }) {
  const fallback = [
    {
      id: "sys1",
      action: "Frontend загружен без ошибок",
      actor: "Система",
      timestamp: new Date().toISOString(),
    },
    {
      id: "sys2",
      action: "Mock-репозиторий инициализирован",
      actor: "Система",
      timestamp: new Date().toISOString(),
    },
    {
      id: "sys3",
      action: "Проверена структура данных",
      actor: "Администратор",
      timestamp: new Date().toISOString(),
    },
  ];
  return (
    <div className="system-events">
      {(data.audit.length ? data.audit : fallback).slice(0, 8).map((e) => (
        <div key={e.id}>
          <ShieldCheck />
          <span>
            <strong>{e.action}</strong>
            <small>
              {e.actor} · {new Date(e.timestamp).toLocaleString("ru-RU")}
            </small>
          </span>
        </div>
      ))}
    </div>
  );
}
function Range({
  label,
  value,
  min,
  max,
  hint,
  signed = false,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  hint: string;
  signed?: boolean;
  onChange: (v: number) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  const percent = Math.max(
    0,
    Math.min(100, ((value - min) / (max - min)) * 100),
  );
  const display = signed && value > 0 ? `+${value}` : String(value);
  function commit(raw: string) {
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      setDraft(String(value));
      return;
    }
    const next = Math.max(min, Math.min(max, Math.round(parsed)));
    setDraft(String(next));
    onChange(next);
  }
  return (
    <label className="range-field">
      <span>
        <strong>{label}</strong>
        <em>{display}</em>
      </span>
      <div className="range-control">
        <input
          className={`gradient-range ${signed ? "signed" : "positive"}`}
          aria-label={`${label}: ползунок`}
          type="range"
          min={min}
          max={max}
          step={1}
          value={value}
          style={{ "--range-position": `${percent}%` } as React.CSSProperties}
          onChange={(e) => onChange(Number(e.target.value))}
        />
        <input
          className="range-number"
          aria-label={`${label}: введите целое число`}
          type="number"
          inputMode="numeric"
          min={min}
          max={max}
          step={1}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            if (e.target.value !== "") commit(e.target.value);
          }}
          onBlur={() => commit(draft)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit(draft);
          }}
        />
      </div>
      <div className="range-scale">
        <span>{min}</span>
        {min < 0 && max > 0 && <b>0 · нейтрально</b>}
        <span>{signed ? `+${max}` : max}</span>
      </div>
      <small>{hint}</small>
    </label>
  );
}
function formatSignedState(value: number | undefined) {
  if (value === undefined) return "—";
  const signed = Math.round((value - 5) * 2);
  if (signed === 0) return "0 · нейтрально";
  return `${signed > 0 ? "+" : "−"}${Math.abs(signed)} · ${signed > 0 ? "выше" : "ниже"}`;
}

export function PatientPortalReadOnly({ onLogout }: { onLogout: () => void }) {
  const [data, setData] = useState<AppData>(createSeed());
  const [dataReady,setDataReady]=useState(false);
  const [loadError,setLoadError]=useState('');
  const [page, setPage] = useState<PatientPage>("home");
  const [maxLink, setMaxLink] = useState<MaxLinkCode | null>(null);
  const [maxBusy, setMaxBusy] = useState(false);
  const [maxError, setMaxError] = useState("");
  useEffect(() => {
    import("@/services")
      .then(({ repository }) => repository().getData())
      .then(value=>{setData(value);setDataReady(true);}).catch(()=>setLoadError('Не удалось загрузить данные. Проверьте подключение к серверу.'));
  }, []);
  if(!dataReady)return <div className="state-page" role="status">{loadError||'Загрузка данных…'}{loadError&&<button className="outline" onClick={()=>window.location.reload()}>Повторить загрузку</button>}<button className="text-button" onClick={onLogout}>Выйти</button></div>;
  const patient = data.patients[0];
  if (!patient) return <div className="splash">Данные пациента не найдены</div>;
  const navigation: [PatientPage, string, typeof LayoutDashboard][] = [
    ["home", "Главная", LayoutDashboard],
    ["diary", "История наблюдения", HeartPulse],
    ["therapy", "Назначения", Pill],
    ["tasks", "Опросники", ListChecks],
    ["documents", "Документы", FileCheck2],
    ["profile", "Профиль", UserRound],
  ];
  const patientTasks = data.assignments.filter(
    (task) => task.patientId === patient.id,
  );
  async function requestMaxCode() {
    setMaxBusy(true);
    setMaxError("");
    try {
      const result = await import("@/services").then(({ repository }) =>
        repository().createOwnMaxLinkCode(),
      );
      setMaxLink(result);
    } catch (reason) {
      setMaxError(
        reason instanceof Error ? reason.message : "Не удалось создать код MAX",
      );
    } finally {
      setMaxBusy(false);
    }
  }
  async function copyMaxCode() {
    if (maxLink) await navigator.clipboard.writeText(maxLink.code);
  }
  return (
    <PortalFrame
      title="Кабинет пациента"
      subtitle="История наблюдения и назначения"
      nav={navigation}
      page={page}
      setPage={setPage}
      onLogout={onLogout}
      initials="АК"
      showRoleLabel={false}
    >
      <div className="patient-welcome">
        <div>
          <h1>
            {page === "home"
              ? `Здравствуйте, ${patient.name}`
              : navigation.find((item) => item[0] === page)?.[1]}
          </h1>
          <p>
            {page === "home"
              ? "Отвечайте на вопросы врача в MAX. На сайте доступна ваша история наблюдения."
              : "Сведения доступны только в защищённом кабинете."}
          </p>
        </div>
        {page === "home" && (
          <button className="outline" onClick={() => setPage("diary")}>
            <HeartPulse size={18} />
            Открыть историю
          </button>
        )}
      </div>
      {page === "home" && (
        <>
          <InfoNote>
            Ответы, дневник состояния и отметки о выполнении собираются только в
            MAX. Бот не показывает медицинскую карту, результаты и историю.
          </InfoNote>
          <div className="patient-kpis">
            <Kpi
              icon={HeartPulse}
              value={formatSignedState(patient.dynamics.at(-1)?.wellbeing)}
              label="Последнее состояние"
              tone="blue"
            />
            <Kpi
              icon={Clock3}
              value={`${patient.dynamics.at(-1)?.sleep} ч`}
              label="Сон"
              tone="violet"
            />
            <Kpi
              icon={Pill}
              value={`${patient.adherence}%`}
              label="Приверженность"
              tone="green"
            />
            <Kpi
              icon={ListChecks}
              value={
                patientTasks.filter((task) => task.status === "assigned").length
              }
              label="Ожидают ответа в MAX"
              tone="red"
            />
          </div>
          <div className="patient-home-grid">
            <section className="card">
              <DynamicsChart data={patient.dynamics} compact />
            </section>
            <section className="card next-action">
              <h2>Ближайшее событие</h2>
              <span className="patient-action-icon">
                <CalendarDays size={25} />
              </span>
              <strong>Повторная консультация</strong>
              <p>Дата появится после приглашения врача</p>
              <button className="outline" onClick={() => setPage("tasks")}>
                Опросники
                <ChevronRight size={16} />
              </button>
            </section>
          </div>
        </>
      )}
      {page === "diary" && (
        <section className="card">
          <div className="section-heading">
            <div>
              <h2>История состояния</h2>
              <p>Данные из ответов, отправленных через MAX</p>
            </div>
            <Badge risk="green" text="Только просмотр" />
          </div>
          <DynamicsChart data={patient.dynamics} />
          <InfoNote>
            Новая запись появится после прохождения назначенного опроса в MAX.
          </InfoNote>
        </section>
      )}
      {page === "therapy" && (
        <section className="card">
          <h2>Назначения врача</h2>
          <InfoNote>
            Отметки о приёме передаются только через MAX, если лечащий врач
            включил такой вопрос.
          </InfoNote>
          {patient.prescriptions.map((rx) => (
            <article className="therapy-patient-card" key={rx.id}>
              <div>
                <h3>{rx.medication.name}</h3>
                <p>{rx.regimen}</p>
              </div>
              <Badge risk="green" text="Назначено" />
            </article>
          ))}
        </section>
      )}
      {page === "tasks" && (
        <section className="card">
          <h2>Назначенные опросники</h2>
          <InfoNote>
            MAX пришлёт вопросы по расписанию врача. Здесь отображается только
            состояние назначения.
          </InfoNote>
          {patientTasks.map((task) => (
            <article className="patient-list-row" key={task.id}>
              <ListChecks />
              <div>
                <strong>{task.template}</strong>
                <p>
                  {new Date(task.dueAt).toLocaleString("ru-RU", {
                    day: "numeric",
                    month: "long",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
              <Badge
                risk={task.status === "completed" ? "green" : "yellow"}
                text={task.status === "completed" ? "Выполнено" : "Ожидается в MAX"}
              />
            </article>
          ))}
        </section>
      )}
      {page === "documents" && (
        <section className="card">
          <h2>Мои документы</h2>
          <Empty
            title="Документы не загружены"
            text="Загруженные документы появятся в этом разделе."
          />
        </section>
      )}
      {page === "profile" && (
        <section className="card patient-profile">
          <Avatar patient={patient} />
          <div>
            <h2>{patient.name}</h2>
            <p>Карта {patient.card}</p>
            <small>
              {patient.age} лет · лечащий врач: {patient.doctor}
            </small>
          </div>
          <InfoNote>
            Медицинские сведения и история доступны через сайт и не передаются
            ботом MAX.
          </InfoNote>
          <div className="patient-max-access">
            <span className="patient-max-icon">
              <KeyRound size={23} />
            </span>
            <div>
              <h3>Подключение к боту MAX</h3>
              <p>
                Получите одноразовый код и отправьте его боту. Код действует 24
                часа.
              </p>
            </div>
            <button
              className="primary"
              disabled={maxBusy}
              onClick={requestMaxCode}
            >
              {maxBusy ? (
                <LoaderCircle className="spin" size={18} />
              ) : (
                <KeyRound size={18} />
              )}
              {maxLink ? "Получить новый код" : "Получить код MAX"}
            </button>
            {maxLink && (
              <div className="patient-max-code">
                <span>
                  <small>Ваш одноразовый код</small>
                  <strong>{maxLink.code}</strong>
                  <em>
                    Действует до{" "}
                    {new Date(maxLink.expiresAt).toLocaleString("ru-RU")}
                  </em>
                </span>
                <button className="outline" onClick={copyMaxCode}>
                  <Copy size={17} />
                  Копировать
                </button>
              </div>
            )}
            {maxError && <p className="patient-max-error">{maxError}</p>}
          </div>
        </section>
      )}
    </PortalFrame>
  );
}
