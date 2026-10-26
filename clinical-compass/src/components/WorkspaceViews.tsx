"use client";
import { useEffect, useState, useRef } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  Download,
  FileText,
  LoaderCircle,
  MessageCircle,
  Pencil,
  Plus,
  Send,
  ShieldCheck,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import type {
  Account,
  AiRecommendation,
  AiStatus,
  ClinicalAlert,
  ClinicalTask,
  MessageConversation,
  PatientMessage,
  Settings,
} from "@/types";
import { formatDate, repository } from "@/services";
import { useApp } from "./AppContext";
import { DraftVerification } from "./DraftVerification";
import { MedicationReviewForm } from "./MedicationReviewForm";
import { Avatar, Badge, Empty, InfoNote, SearchField, SourceLink } from "./ui";

export function Alerts() {
  const { data, modal, search, setSearch, run } = useApp();
  const [kind, setKind] = useState("active");
  const [level, setLevel] = useState("all");
  const filtered = data.alerts
    .filter(
      (a) =>
        (kind === "closed" ? a.status === "closed" : a.status !== "closed") &&
        (level === "all" || a.level === level) &&
        `${data.patients.find((p) => p.id === a.patientId)?.name} ${a.reason}`
          .toLowerCase()
          .includes(search.toLowerCase()),
    )
    .sort(
      (a, b) =>
        ({ red: 0, yellow: 1, green: 2 })[a.level] -
        { red: 0, yellow: 1, green: 2 }[b.level],
    );
  async function openAlert(alert: ClinicalAlert) {
    let next = alert;
    if (alert.status === "new") {
      await run(
        () =>
          repository().updateAlert(alert.id, {
            status: "working",
            comment: alert.comment,
            action: alert.action,
          }),
        "Уведомление отмечено просмотренным",
      );
      next = { ...alert, status: "working" };
    }
    modal({ type: "alert", alert: next });
  }
  return (
    <>
      <PageTitle
        title="Уведомления"
        subtitle="Сигналы, которые требуют внимания врача"
      />
      <section className="card">
        <div className="filter-row">
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder="Поиск по пациенту или причине…"
          />
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value)}
            aria-label="Уровень уведомления"
          >
            <option value="all">Все уровни</option>
            <option value="red">Критические</option>
            <option value="yellow">Требуют внимания</option>
            <option value="green">Информационные</option>
          </select>
          <div className="tabs-pills">
            <button
              className={kind === "active" ? "active" : ""}
              onClick={() => setKind("active")}
            >
              Активные
            </button>
            <button
              className={kind === "closed" ? "active" : ""}
              onClick={() => setKind("closed")}
            >
              Закрытые
            </button>
          </div>
        </div>
        <div className="alert-list">
          {filtered.map((a) => (
            <AlertRow key={a.id} alert={a} onOpen={() => openAlert(a)} />
          ))}
        </div>
        {!filtered.length && (
          <Empty
            title="Уведомления не найдены"
            text="Измените фильтры или откройте закрытые сигналы."
          />
        )}
      </section>
    </>
  );
}
function AlertRow({
  alert,
  onOpen,
}: {
  alert: ClinicalAlert;
  onOpen: () => void;
}) {
  const { data, navigate } = useApp();
  const p = data.patients.find((p) => p.id === alert.patientId);
  return (
    <article className={`alert-row ${alert.level}`}>
      <Badge
        risk={alert.level}
        text={
          alert.status === "closed"
            ? "Закрыт"
            : alert.status === "working"
              ? "В работе"
              : "Новый"
        }
      />
      <button
        className="patient-cell alert-patient"
        onClick={() => navigate("patient", alert.patientId)}
      >
        {p && <Avatar patient={p} small />}
        <span>
          <strong>{p?.name || "Пациент"}</strong>
          <small>
            <span>{p?.diagnosis.code}</span>
            <span>{p?.age} лет</span>
          </small>
        </span>
      </button>
      <div className="alert-copy">
        <strong>{alert.reason}</strong>
        <p>{alert.source}</p>
        <small>
          Возник: {formatDate(alert.createdAt, true)} · Доставлен:{" "}
          {formatDate(alert.deliveredAt, true)}
        </small>
      </div>
      <button className="outline" onClick={onOpen}>
        Открыть
        <ChevronRight size={16} />
      </button>
    </article>
  );
}

export function Tasks() {
  const { data, modal, run } = useApp();
  const [status, setStatus] = useState<"all" | ClinicalTask["status"]>("all");
  const [view, setView] = useState<"list" | "calendar">("list");
  const today = new Date();
  const dateKey = (date: Date) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const [selectedDay, setSelectedDay] = useState(() => dateKey(new Date()));
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() + index - 2);
    return date;
  });
  const statusFilters = [
    ["all", "Все"],
    ["new", "Новые"],
    ["working", "В работе"],
    ["done", "Выполненные"],
    ["cancelled", "Отменённые"],
  ] as const;
  const filtered = data.tasks
    .filter(
      (task) =>
        (status === "all" || task.status === status) &&
        (view !== "calendar" || task.dueAt.slice(0, 10) === selectedDay),
    )
    .sort((first, second) => first.dueAt.localeCompare(second.dueAt));
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Задания</h1>
          <p>Планы, сроки и действия врача</p>
        </div>
        <button className="primary" onClick={() => modal({ type: "task" })}>
          <Plus size={18} />
          Создать задачу
        </button>
      </div>
      <section className="card">
        <div className="task-toolbar">
          <div
            className="task-status-filter"
            role="group"
            aria-label="Фильтр по статусу"
          >
            {statusFilters.map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={status === value ? "active" : ""}
                aria-pressed={status === value}
                onClick={() => setStatus(value)}
              >
                {label}
                <span>
                  {value === "all"
                    ? data.tasks.length
                    : data.tasks.filter((task) => task.status === value).length}
                </span>
              </button>
            ))}
          </div>
          <div className="tabs-pills">
            <button
              className={view === "list" ? "active" : ""}
              onClick={() => setView("list")}
            >
              Список
            </button>
            <button
              className={view === "calendar" ? "active" : ""}
              onClick={() => setView("calendar")}
            >
              По срокам
            </button>
          </div>
        </div>
        {view === "calendar" && (
          <div className="calendar-strip" aria-label="Выберите дату">
            {days.map((date) => {
              const day = dateKey(date);
              return (
                <button
                  type="button"
                  className={selectedDay === day ? "today" : ""}
                  aria-pressed={selectedDay === day}
                  onClick={() => setSelectedDay(day)}
                  key={day}
                >
                  <small>
                    {date.toLocaleDateString("ru-RU", { weekday: "short" })}
                  </small>
                  <strong>
                    {date.toLocaleDateString("ru-RU", {
                      day: "numeric",
                      month: "short",
                    })}
                  </strong>
                  <span>
                    {
                      data.tasks.filter(
                        (task) => task.dueAt.slice(0, 10) === day,
                      ).length
                    }{" "}
                    задач
                  </span>
                </button>
              );
            })}
          </div>
        )}
        <div className="task-list">
          {filtered.map((task) => {
            const patient = data.patients.find(
              (item) => item.id === task.patientId,
            );
            const overdue =
              new Date(task.dueAt).getTime() < Date.now() &&
              task.status !== "done" &&
              task.status !== "cancelled";
            const tone =
              task.status === "done"
                ? "green"
                : task.status === "working"
                  ? "yellow"
                  : "gray";
            return (
              <article className="task-row" key={task.id}>
                <div>
                  <strong>{task.title}</strong>
                  <p>
                    {patient?.name} · {formatDate(task.dueAt, true)}{" "}
                    {overdue && <em className="task-overdue">Просрочено</em>}
                  </p>
                </div>
                <span className={`badge ${tone}`}>
                  {taskStatus(task.status)}
                </span>
                <label className="task-status-select">
                  <span className="sr-only">Статус задания</span>
                  <select
                    aria-label={`Статус задания: ${task.title}`}
                    value={task.status}
                    onChange={(event) =>
                      run(
                        () =>
                          repository().updateTask(
                            task.id,
                            event.target.value as ClinicalTask["status"],
                          ),
                        "Статус задачи обновлён",
                      )
                    }
                  >
                    <option value="new">Новое</option>
                    <option value="working">В работе</option>
                    <option value="done">Выполнено</option>
                    <option value="cancelled">Отменено</option>
                  </select>
                </label>
              </article>
            );
          })}
        </div>
        {!filtered.length && (
          <Empty
            title="Заданий с таким статусом нет"
            text="Выберите другой статус или дату."
          />
        )}
      </section>
    </>
  );
}
function taskStatus(s: ClinicalTask["status"]) {
  return (
    {
      new: "Новое",
      working: "В работе",
      done: "Выполнено",
      cancelled: "Отменено",
    } as const
  )[s];
}

const aiActions = [
  ["summary", "Краткое резюме пациента"],
  ["changes", "Найти изменения состояния"],
  ["risks", "Проверить факторы риска"],
  ["sources", "Найти клинические источники"],
  ["medication", "Проверить карточку препарата"],
  ["note", "Подготовить черновик записи"],
  ["questions", "Вопросы к следующему визиту"],
];
export function AiAssistant() {
  const { data, selectedId, run, busy, toast } = useApp();
  const [patientId, setPatientId] = useState(
    selectedId || data.patients[0]?.id || "",
  );
  const [kind, setKind] = useState("summary");
  const [activeId, setActiveId] = useState(
    data.recommendations.find((r) => r.patientId === patientId)?.id || "",
  );
  const [confirm, setConfirm] = useState(false);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  useEffect(() => {
    repository()
      .getAiStatus()
      .then(setAiStatus)
      .catch(() =>
        setAiStatus({
          provider: "ollama",
          model: "qwen3:4b-instruct",
          available: false,
          message: "Статус модели недоступен",
        }),
      );
  }, []);
  const recommendation =
    data.recommendations.find((r) => r.id === activeId) ||
    data.recommendations.find((r) => r.patientId === patientId);
  const [draft, setDraft] = useState("");
  const currentText = draft || recommendation?.text || "";
  async function generate() {
    setConfirm(false);
    let created: AiRecommendation | undefined;
    const ok = await run(async () => {
      created = await repository().generateAi({ patientId, kind });
    }, "Черновик готов");
    if (ok && created) {
      setActiveId(created.id);
      setDraft(created.text);
    }
    repository().getAiStatus().then(setAiStatus).catch(() => {});
  }
  async function save(status: AiRecommendation["status"]) {
    if (!recommendation) return;
    if (status === "accepted" && !confirm) {
      toast("Поставьте отметку о проверке решения врачом");
      return;
    }
    if (
      await run(
        () =>
          repository().updateAi(
            recommendation.id,
            currentText,
            status,
            confirm,
          ),
        status === "accepted" ? "Решение врача сохранено" : "Черновик обновлён",
      )
    )
      setDraft("");
  }
  return (
    <>
      <div className="page-heading ai-page-heading">
        <div>
          <h1>ИИ-рекомендации</h1>
          <p>Динамика пациента, факторы для проверки и клинический черновик</p>
        </div>
        <span className={`ai-runtime ${aiStatus?.available ? "ready" : "fallback"}`} title={aiStatus?.message}>
          <i />
          {aiStatus?.model || "Qwen3-4B"} · {aiStatus?.available ? "локально" : "правила"}
        </span>
      </div>
      <div className="ai-warning">
        <AlertTriangle size={22} />
        <span>
          <strong>
            ИИ помогает подготовить решение, но не назначает лечение.
          </strong>{" "}
          Допуск препарата рассчитывается по правилам, решение принимает врач.
        </span>
      </div>
      <div className="ai-workflow" aria-label="Порядок формирования рекомендации">
        <span>Показатели пациента</span><ArrowRight size={16} />
        <span>Проверка правил</span><ArrowRight size={16} />
        <span>Черновик Qwen</span><ArrowRight size={16} />
        <span>Решение врача</span>
      </div>
      <div className="ai-layout">
        <aside className="card ai-history">
          <h3>История запросов</h3>
          {data.recommendations.length ? (
            data.recommendations.map((r) => (
              <button
                className={r.id === recommendation?.id ? "active" : ""}
                disabled={busy}
                key={r.id}
                onClick={() => {
                  setActiveId(r.id);
                  setPatientId(r.patientId);
                  setDraft("");
                  setConfirm(false);
                }}
              >
                <Sparkles size={17} />
                <span>
                  {aiActions.find((a) => a[0] === r.kind)?.[1] || r.kind}
                  <small>
                    {data.patients.find((p) => p.id === r.patientId)?.name} ·{" "}
                    {formatDate(r.createdAt, true)}
                  </small>
                </span>
              </button>
            ))
          ) : (
            <Empty
              title="Запросов ещё нет"
              text="Выберите сценарий и сформируйте черновик."
            />
          )}
        </aside>
        <main className="card ai-chat">
          <div className="filter-row">
            <select
              value={patientId}
              disabled={busy}
              onChange={(e) => {
                setPatientId(e.target.value);
                setActiveId("");
                setDraft("");
                setConfirm(false);
              }}
              aria-label="Пациент"
            >
              {data.patients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <select
              value={kind}
              disabled={busy}
              onChange={(e) => setKind(e.target.value)}
              aria-label="Тип запроса"
            >
              {aiActions.map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
            <button
              className="primary"
              onClick={generate}
              disabled={!patientId || busy}
            >
              {busy ? (
                <LoaderCircle className="spin" size={18} />
              ) : (
                <Sparkles size={18} />
              )}
              Сформировать
            </button>
          </div>
          {patientId && <MedicationReviewForm key={patientId} patientId={patientId} />}
          {recommendation ? (
            <>
              <div className="ai-message user-message">
                Подготовьте:{" "}
                {aiActions.find((a) => a[0] === recommendation.kind)?.[1]}
              </div>
              <article className="ai-answer">
                <div className="answer-label">
                  <Sparkles size={18} />
                  ИИ-черновик
                </div>
                <textarea
                  aria-label="Текст черновика"
                  value={currentText}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={8}
                />
                <DraftVerification
                  verification={recommendation.verification}
                  edited={Boolean(draft) && draft !== recommendation.text}
                />
                <h4>Использованные данные</h4>
                <p>{recommendation.data}</p>
                <h4>Факторы для проверки</h4>
                <p>{recommendation.risks}</p>
                <h4>Ограничения</h4>
                <p>{recommendation.limitations}</p>
                <div className="ai-actions">
                  <button className="outline" onClick={() => save("draft")}>
                    <Pencil size={16} />
                    Сохранить правки
                  </button>
                  <button
                    className="outline danger-outline"
                    onClick={() => save("rejected")}
                  >
                    <X size={16} />
                    Отклонить
                  </button>
                </div>
                <label className="confirm-box">
                  <input
                    type="checkbox"
                    checked={confirm}
                    onChange={(e) => setConfirm(e.target.checked)}
                  />
                  <span>
                    Я проверил(а) черновик и самостоятельно принял(а)
                    клиническое решение.
                  </span>
                </label>
                <button className="primary" onClick={() => save("accepted")}>
                  <Check size={17} />
                  Подтвердить решение врача
                </button>
              </article>
            </>
          ) : (
            <Empty
              title="Выберите действие"
              text="Выберите пациента и нажмите «Сформировать». Локальный Qwen подготовит черновик по данным карточки."
            />
          )}
        </main>
        <aside className="card sources-panel">
          <h3>
            <BookOpen size={19} />
            Источники
          </h3>
          {recommendation?.verification?.citations.map((citation) => (
            <div className="source-card" key={citation.url}>
              <span>КЛИНИЧЕСКИЕ РЕКОМЕНДАЦИИ</span>
              <strong>{citation.title}</strong>
              <small>
                Страница {citation.page}
                {citation.recommendationLevel && <> · уровень {citation.recommendationLevel}</>}
              </small>
              <small className="source-quote">{citation.quote}</small>
              <SourceLink url={citation.url}>Открыть страницу КР</SourceLink>
            </div>
          ))}
          {(recommendation?.sourceIds || ["doc1", "doc2"]).map((id) => {
            const d = data.documents.find((x) => x.id === id);
            return d ? (
              <div className="source-card" key={id}>
                <span>ИСТОЧНИК</span>
                <strong>{d.title}</strong>
                <small>
                  {d.organization}
                  <br />
                  Версия: {d.version}
                  <br />
                  Проверка: {formatDate(d.checked)}
                </small>
                {d.url && (
                  <SourceLink url={d.url}>Официальный каталог</SourceLink>
                )}
              </div>
            ) : null;
          })}
          <InfoNote>
            Содержание внешних сайтов не загружается в интерфейс. Врач открывает
            официальный каталог и проверяет актуальный документ самостоятельно.
          </InfoNote>
        </aside>
      </div>
    </>
  );
}

export function Knowledge() {
  const { data, modal, search, setSearch } = useApp();
  const [category, setCategory] = useState("all");
  const filtered = data.documents.filter(
    (d) =>
      (category === "all" || d.category === category) &&
      `${d.title} ${d.organization} ${d.code}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const categories = [...new Set(data.documents.map((d) => d.category))];
  return (
    <>
      <PageTitle
        title="База знаний"
        subtitle="Каталог клинических источников"
      />
      <section className="card">
        <div className="filter-row">
          <SearchField
            value={search}
            onChange={setSearch}
            placeholder="Поиск по документам и кодам…"
          />
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            aria-label="Категория"
          >
            <option value="all">Все категории</option>
            {categories.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
        <InfoNote>
          Карточки носят справочный характер. Перед использованием врач должен
          открыть официальный источник и проверить актуальность, версию и
          применимость.
        </InfoNote>
        <div className="document-grid">
          {filtered.map((d) => (
            <button
              className="knowledge-card"
              key={d.id}
              onClick={() => modal({ type: "document", document: d })}
            >
              <span className="doc-icon">
                <FileText size={23} />
              </span>
              <span className="eyebrow">{d.category}</span>
              <strong>{d.title}</strong>
              <p>{d.organization}</p>
              <small>
                Версия {d.version} · Проверено {formatDate(d.checked)}
              </small>
              <span className="text-button">
                Открыть карточку
                <ArrowRight size={15} />
              </span>
            </button>
          ))}
        </div>
        {!filtered.length && <Empty />}
      </section>
    </>
  );
}

export function Reports() {
  const { data, toast } = useApp();
  const reports = [
    ["Динамика состояния пациента", "Графики самооценки и заполнения дневника"],
    ["Приверженность терапии", "Отметки и пропуски в дневнике пациента"],
    ["Обработка сигналов", "Время реакции и статусы сигналов"],
    ["Активность пациентов", "Дневники и опросники между визитами"],
    ["Нагрузка врача", "Задачи и действия в журнале"],
  ];
  return (
    <>
      <PageTitle title="Отчёты" subtitle="Сводная аналитика данных" />
      <div className="report-grid">
        {reports.map(([title, desc], i) => (
          <section className="card report-card" key={title}>
            <span className="doc-icon">
              <FileText size={23} />
            </span>
            <h3>{title}</h3>
            <p>{desc}</p>
            <div className="mini-bars">
              {[55, 76, 38, 88, 64, 92, 70].map((v, j) => (
                <span
                  style={{ height: `${((v + i * 7) % 90) + 10}%` }}
                  key={j}
                />
              ))}
            </div>
            <button
              className="outline"
              onClick={() => toast("Экспорт PDF пока не подключён.")}
            >
              <Download size={16} />
              Экспортировать PDF
            </button>
          </section>
        ))}
      </div>
      <section className="card">
        <h3>Краткая сводка</h3>
        <div className="stat-grid">
          <div className="stat-card">
            <strong>{data.patients.length}</strong>
            <span>Пациентов</span>
          </div>
          <div className="stat-card">
            <strong>
              {data.alerts.filter((a) => a.status === "closed").length}
            </strong>
            <span>Закрыто сигналов</span>
          </div>
          <div className="stat-card">
            <strong>
              {data.tasks.filter((t) => t.status === "done").length}
            </strong>
            <span>Выполнено задач</span>
          </div>
          <div className="stat-card">
            <strong>{data.audit.length}</strong>
            <span>Событий аудита</span>
          </div>
        </div>
      </section>
    </>
  );
}

export function Messages() {
  const { toast } = useApp();
  const [conversations, setConversations] = useState<MessageConversation[]>([]);
  const [selected, setSelected] = useState("");
  const [messages, setMessages] = useState<PatientMessage[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const draft = drafts[selected] || "";
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  function setDraft(text: string) {
    setDrafts((value) => ({ ...value, [selected]: text }));
  }
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const current = conversations.find((item) => item.patientId === selected);
  async function loadConversations() {
    const rows = await repository().getMessageConversations();
    setConversations(rows);
    setSelected((value) => value || rows[0]?.patientId || "");
  }
  useEffect(() => {
    loadConversations()
      .catch((error) =>
        toast(
          error instanceof Error
            ? error.message
            : "Не удалось загрузить диалоги",
        ),
      )
      .finally(() => setLoading(false));
  }, [toast]);
  useEffect(() => {
    if (!selected) {
      setMessages([]);
      return;
    }
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    setMessages([]);
    async function refresh() {
      try {
        const rows = await repository().getPatientMessages(selected);
        if (active) setMessages(rows);
      } catch (error) {
        if (active)
          toast(
            error instanceof Error
              ? error.message
              : "Не удалось открыть переписку",
          );
      } finally {
        if (active) {
          setLoading(false);
          timer = setTimeout(refresh, 5000);
        }
      }
    }
    void refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [selected, toast]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    const patientId = selected;
    if (!text || !patientId) return;
    setSending(true);
    try {
      const item = await repository().sendPatientMessage(patientId, text);
      if (selectedRef.current === patientId)
        setMessages((value) =>
          value.some((row) => row.id === item.id) ? value : [...value, item],
        );
      setDrafts((value) => ({ ...value, [patientId]: "" }));
      await loadConversations();
    } catch (error) {
      toast(error instanceof Error ? error.message : "Сообщение не отправлено");
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <PageTitle
        title="Сообщения"
        subtitle="Защищённый канал связи с пациентами через MAX"
      />
      <section className="message-workspace card">
        <aside className="conversation-list" aria-label="Диалоги с пациентами">
          <header>
            <h2>Пациенты</h2>
            <span>
              {conversations.reduce((sum, item) => sum + item.unreadCount, 0)}{" "}
              новых
            </span>
          </header>
          {conversations.map((item) => (
            <button
              key={item.patientId}
              className={selected === item.patientId ? "active" : ""}
              onClick={() => setSelected(item.patientId)}
            >
              <span className="conversation-avatar">
                <UserRound size={20} />
              </span>
              <span>
                <strong>{item.patientName}</strong>
                <small>
                  {item.lastMessage?.text || "Переписка ещё не начата"}
                </small>
              </span>
              <span className="conversation-meta">
                <i className={item.maxConnected ? "online" : ""} />
                {item.unreadCount > 0 && <em>{item.unreadCount}</em>}
              </span>
            </button>
          ))}
          {!loading && !conversations.length && (
            <Empty
              title="Пациентов нет"
              text="Диалоги появятся после добавления пациентов."
            />
          )}
        </aside>
        <div className="message-thread">
          {current ? (
            <>
              <header>
                <div>
                  <strong>{current.patientName}</strong>
                  <small>
                    {current.card} ·{" "}
                    {current.maxConnected
                      ? "MAX подключён"
                      : "MAX ещё не подключён"}
                  </small>
                </div>
                <span
                  className={
                    current.maxConnected
                      ? "connection-ready"
                      : "connection-wait"
                  }
                >
                  {current.maxConnected
                    ? "Можно отправлять"
                    : "Ожидается подключение"}
                </span>
              </header>
              <div className="message-history" aria-live="polite">
                {loading ? (
                  <LoaderCircle className="spin" size={28} />
                ) : messages.length ? (
                  messages.map((item) => (
                    <article
                      key={item.id}
                      className={
                        item.senderRole === "doctor"
                          ? "from-doctor"
                          : "from-patient"
                      }
                    >
                      <p>{item.text}</p>
                      <small>
                        {item.senderRole === "doctor" ? "Вы" : "Пациент"} ·{" "}
                        {formatDate(item.createdAt, true)}
                      </small>
                    </article>
                  ))
                ) : (
                  <div className="message-empty">
                    <MessageCircle size={34} />
                    <h3>Начните диалог</h3>
                    <p>
                      Ответ врача придёт пациенту в MAX. Сообщения пациента
                      появятся здесь.
                    </p>
                  </div>
                )}
              </div>
              <form className="message-composer" onSubmit={submit}>
                <textarea
                  aria-label="Сообщение пациенту"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  rows={2}
                  maxLength={4000}
                  placeholder={
                    current.maxConnected
                      ? "Напишите сообщение пациенту…"
                      : "Пациент должен завершить подключение MAX"
                  }
                  disabled={!current.maxConnected || sending}
                />
                <button
                  className="primary"
                  disabled={!draft.trim() || !current.maxConnected || sending}
                >
                  {sending ? (
                    <LoaderCircle className="spin" size={18} />
                  ) : (
                    <Send size={18} />
                  )}
                  Отправить
                </button>
              </form>
            </>
          ) : (
            <div className="message-empty">
              <MessageCircle size={38} />
              <h3>Выберите пациента</h3>
              <p>
                Откройте диалог, чтобы увидеть сообщения и ответить через MAX.
              </p>
            </div>
          )}
        </div>
      </section>
    </>
  );
}

export function SettingsView() {
  const { data, run, toast } = useApp();
  const [section, setSection] = useState("profile");
  const [settings, setSettings] = useState<Settings>(data.settings);
  const [account, setAccount] = useState<Account | null>(null);
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const sections = [
    ["profile", "Профиль и контакты"],
    ["security", "Безопасность"],
    ["notifications", "Уведомления"],
    ["alerting", "Параметры уведомлений"],
    ["audit", "Аудит"],
  ];
  useEffect(() => {
    repository()
      .getAccount()
      .then((value) => {
        setAccount(value);
        setEmail(value.email || "");
        setPhone(value.phone || "");
      })
      .catch((reason) =>
        toast(
          reason instanceof Error
            ? reason.message
            : "Не удалось загрузить контакты",
        ),
      );
  }, [toast]);
  async function saveContact() {
    await run(async () => {
      const updated = await repository().saveContact(email, phone);
      setAccount(updated);
      setEmail(updated.email || "");
      setPhone(updated.phone || "");
    }, "Контактные данные сохранены");
  }
  return (
    <>
      <PageTitle title="Настройки" subtitle="Параметры рабочей среды" />
      <div className="settings-layout">
        <nav className="card settings-nav">
          {sections.map(([id, label]) => (
            <button
              key={id}
              className={section === id ? "active" : ""}
              onClick={() => setSection(id)}
            >
              {label}
              <ChevronRight size={15} />
            </button>
          ))}
        </nav>
        <section className="card settings-content">
          {section === "profile" && (
            <>
              <h2>Профиль и контакты</h2>
              <InfoNote>
                ФИО, специальность и организацию изменяет администратор. Вы
                можете самостоятельно обновить только привязанные почту и
                телефон.
              </InfoNote>
              <div className="setting-line">
                <div>
                  <strong>ФИО</strong>
                  <p>{data.settings.name}</p>
                </div>
                <span className="badge green">Администратор</span>
              </div>
              <div className="setting-line">
                <div>
                  <strong>Специальность</strong>
                  <p>{data.settings.specialty}</p>
                </div>
                <span className="badge green">Администратор</span>
              </div>
              <div className="setting-line">
                <div>
                  <strong>Организация</strong>
                  <p>{data.settings.organization}</p>
                </div>
                <span className="badge green">Администратор</span>
              </div>
              <div className="contact-form">
                <label>
                  Электронная почта
                  <input
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="doctor@example.ru"
                  />
                </label>
                <label>
                  Номер телефона
                  <input
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    placeholder="+7 999 000-00-00"
                  />
                </label>
                <button
                  className="primary"
                  disabled={!account}
                  onClick={saveContact}
                >
                  Сохранить контакты
                </button>
              </div>
            </>
          )}
          {section === "security" && (
            <>
              <h2>Безопасность</h2>
              <InfoNote>
                Вход выполняется через FastAPI, пароль хранится только в виде
                защищённого хеша, а сессия передаётся в HttpOnly cookie.
              </InfoNote>
              <div className="setting-line">
                <div>
                  <strong>Изменение профиля врача</strong>
                  <p>
                    ФИО и профессиональные данные защищены ролью администратора
                  </p>
                </div>
                <span className="badge green">Защищено</span>
              </div>
            </>
          )}
          {section === "notifications" && (
            <>
              <h2>Уведомления</h2>
              <Toggle
                label="Критические сигналы"
                checked={settings.notifications}
                onChange={(value) =>
                  setSettings({ ...settings, notifications: value })
                }
              />
              <Toggle
                label="Напоминания о задачах"
                checked={settings.reminders}
                onChange={(value) =>
                  setSettings({ ...settings, reminders: value })
                }
              />
              <button
                className="primary"
                onClick={() =>
                  run(
                    () => repository().saveSettings(settings),
                    "Настройки сохранены",
                  )
                }
              >
                Сохранить
              </button>
            </>
          )}
          {section === "alerting" && (
            <>
              <h2>Параметры уведомлений</h2>
              <InfoNote>
                Пороги в прототипе условные и не валидированы. Реальные правила
                должен утвердить ответственный врач и организация.
              </InfoNote>
              <div className="setting-line">
                <div>
                  <strong>Пропуски отметок</strong>
                  <p>Создать сигнал после 3 пропусков</p>
                </div>
                <span className="badge yellow">Требует настройки</span>
              </div>
              <div className="setting-line">
                <div>
                  <strong>Изменение самооценки</strong>
                  <p>Показать врачу для ручной проверки</p>
                </div>
                <span className="badge yellow">Требует настройки</span>
              </div>
            </>
          )}
          {section === "audit" && (
            <>
              <h2>История действий</h2>
              {data.audit.length ? (
                data.audit.map((item) => {
                  const presentation = auditPresentation(item.action);
                  return (
                    <div className="audit-row" key={item.id}>
                      <ShieldCheck size={18} />
                      <div>
                        <strong>{presentation.title}</strong>
                        <small>
                          {item.actor} · {formatDate(item.timestamp, true)} ·{" "}
                          {item.entityId}
                        </small>
                      </div>
                      <Badge
                        risk={presentation.risk}
                        text={presentation.status}
                      />
                    </div>
                  );
                })
              ) : (
                <Empty
                  title="Журнал пока пуст"
                  text="Действия врача появятся здесь после изменений."
                />
              )}
            </>
          )}
        </section>
      </div>
    </>
  );
}
function auditPresentation(action: string) {
  const match = action.match(/: (done|working|new)$/);
  const code = match?.[1];
  return {
    title: match ? action.slice(0, -match[0].length) : action,
    status:
      code === "done"
        ? "Выполнено"
        : code === "working"
          ? "В работе"
          : code === "new"
            ? "Новое"
            : "Записано",
    risk: (code === "done"
      ? "green"
      : code === "working"
        ? "yellow"
        : code === "new"
          ? "red"
          : "green") as ClinicalAlert["level"],
  };
}
function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <span className="switch-wrap">
        <input
          className="switch-control"
          type="checkbox"
          role="switch"
          aria-checked={checked}
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="switch-track" aria-hidden="true">
          <span />
        </span>
      </span>
    </label>
  );
}
function PageTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}
