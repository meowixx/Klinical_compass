"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Copy,
  KeyRound,
  LoaderCircle,
  Plus,
  RefreshCw,
  ShieldCheck,
  UserPlus,
  X,
} from "lucide-react";
import type { Account, AdminAccountInput, MaxLinkCode } from "@/types";
import { InfoNote } from "./ui";

const initialForm: AdminAccountInput = {
  login: "",
  password: "",
  name: "",
  role: "patient",
  email: "",
  phone: "",
  specialty: "",
  organization: "",
  patientAge: null,
  patientSex: "Ж",
  diagnosisCode: "",
  doctorId: "",
};

type Confirmation = {
  title: string;
  text: string;
  confirmLabel: string;
  action: () => Promise<void>;
};

export function AdminAccounts({
  notify,
}: {
  notify: (message: string) => void;
}) {
  const notifyRef = useRef(notify);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<AdminAccountInput>(initialForm);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [maxLink, setMaxLink] = useState<{
    patientName: string;
    value: MaxLinkCode;
  } | null>(null);

  const doctors = useMemo(
    () => accounts.filter((account) => account.role === "doctor"),
    [accounts],
  );

  useEffect(() => {
    notifyRef.current = notify;
  }, [notify]);

  useEffect(() => {
    import("@/services")
      .then(({ repository }) => repository().getUsers())
      .then((users) => {
        setAccounts(users);
        const firstDoctor = users.find((account) => account.role === "doctor");
        if (firstDoctor)
          setForm((current) => ({ ...current, doctorId: firstDoctor.id }));
      })
      .catch((reason) =>
        notifyRef.current(
          reason instanceof Error
            ? reason.message
            : "Не удалось загрузить учётные записи",
        ),
      )
      .finally(() => setLoading(false));
  }, []);

  function updateForm<K extends keyof AdminAccountInput>(
    field: K,
    value: AdminAccountInput[K],
  ) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function updateAccountDraft(
    id: string,
    field: "name" | "specialty" | "organization",
    value: string,
  ) {
    setAccounts((current) =>
      current.map((item) =>
        item.id === id ? { ...item, [field]: value } : item,
      ),
    );
  }

  async function runConfirmed() {
    const pending = confirmation;
    if (!pending) return;
    setConfirmation(null);
    await pending.action();
  }

  function requestCreate() {
    if (!form.name.trim() || !form.login.trim() || form.password.length < 8) {
      notify("Укажите ФИО, логин и пароль не короче 8 символов");
      return;
    }
    if (
      form.role === "doctor" &&
      (!form.specialty.trim() || !form.organization.trim())
    ) {
      notify("Укажите специальность и организацию врача");
      return;
    }
    if (
      form.role === "patient" &&
      (!form.patientAge || !form.diagnosisCode.trim() || !form.doctorId)
    ) {
      notify("Укажите возраст, диагноз и лечащего врача пациента");
      return;
    }
    setConfirmation({
      title: "Создать учётную запись?",
      text: `Будет создан ${form.role === "doctor" ? "кабинет врача" : "кабинет пациента"} для «${form.name.trim()}».${form.role === "patient" ? " Код привязки к MAX будет выпущен автоматически на 24 часа." : ""}`,
      confirmLabel: "Создать",
      action: createAccount,
    });
  }

  async function createAccount() {
    setBusy("create");
    try {
      const result = await import("@/services").then(({ repository }) =>
        repository().createUser(form),
      );
      setAccounts((current) => [...current, result.account]);
      if (result.maxLink)
        setMaxLink({ patientName: result.account.name, value: result.maxLink });
      setForm({ ...initialForm, doctorId: doctors[0]?.id || "" });
      setShowCreate(false);
      notify("Учётная запись создана");
    } catch (reason) {
      notify(
        reason instanceof Error
          ? reason.message
          : "Не удалось создать учётную запись",
      );
    } finally {
      setBusy("");
    }
  }

  function requestRoleChange(account: Account, role: "doctor" | "patient") {
    if (account.role === role) return;
    setConfirmation({
      title: "Изменить тип кабинета?",
      text: `Для «${account.name}» кабинет будет изменён на «${role === "doctor" ? "Врач" : "Пациент"}».`,
      confirmLabel: "Изменить роль",
      action: async () => {
        setBusy(account.id);
        try {
          const updated = await import("@/services").then(({ repository }) =>
            repository().updateUserRole(account.id, role),
          );
          setAccounts((current) =>
            current.map((item) => (item.id === updated.id ? updated : item)),
          );
          notify("Тип кабинета изменён");
        } catch (reason) {
          notify(
            reason instanceof Error
              ? reason.message
              : "Не удалось изменить роль",
          );
        } finally {
          setBusy("");
        }
      },
    });
  }

  function requestProfileSave(account: Account) {
    setConfirmation({
      title: "Сохранить изменения профиля?",
      text: `Будут изменены ФИО и профессиональные данные врача «${account.name}».`,
      confirmLabel: "Сохранить",
      action: async () => {
        setBusy(account.id);
        try {
          const updated = await import("@/services").then(({ repository }) =>
            repository().updateUserProfile(account.id, {
              name: account.name,
              specialty: account.specialty || "",
              organization: account.organization || "",
            }),
          );
          setAccounts((current) =>
            current.map((item) => (item.id === updated.id ? updated : item)),
          );
          notify("Профиль врача сохранён");
        } catch (reason) {
          notify(
            reason instanceof Error
              ? reason.message
              : "Не удалось сохранить профиль врача",
          );
        } finally {
          setBusy("");
        }
      },
    });
  }

  function requestMaxCode(account: Account) {
    if (!account.patientId) {
      notify("К учётной записи не привязана карточка пациента");
      return;
    }
    setConfirmation({
      title: "Выпустить новый код MAX?",
      text: `Предыдущий неиспользованный код пациента «${account.name}» перестанет действовать. Новый код будет действителен 24 часа.`,
      confirmLabel: "Выпустить код",
      action: async () => {
        setBusy(account.id);
        try {
          const value = await import("@/services").then(({ repository }) =>
            repository().createMaxLinkCode(account.patientId!),
          );
          setMaxLink({ patientName: account.name, value });
          notify("Новый код MAX создан на 24 часа");
        } catch (reason) {
          notify(
            reason instanceof Error
              ? reason.message
              : "Не удалось создать код MAX",
          );
        } finally {
          setBusy("");
        }
      },
    });
  }

  async function copyCode() {
    if (!maxLink) return;
    await navigator.clipboard.writeText(maxLink.value.code);
    notify("Код MAX скопирован");
  }

  if (loading)
    return (
      <section className="card accounts-loading">
        <LoaderCircle className="spin" />
        Загрузка учётных записей…
      </section>
    );

  return (
    <>
      <section className="card accounts-card">
        <div className="section-heading accounts-heading">
          <div>
            <h2>Учётные записи и профили</h2>
            <p>
              Создание кабинетов, назначение ролей и управление доступом к MAX.
            </p>
          </div>
          <button
            className="primary"
            onClick={() => setShowCreate((value) => !value)}
          >
            {showCreate ? <X size={18} /> : <UserPlus size={18} />}
            {showCreate ? "Закрыть форму" : "Добавить пользователя"}
          </button>
        </div>

        {showCreate && (
          <div className="account-create-panel">
            <div className="account-create-title">
              <span>
                <Plus size={20} />
              </span>
              <div>
                <h3>Новая учётная запись</h3>
                <p>Выберите тип кабинета и заполните данные пользователя.</p>
              </div>
            </div>
            <div className="account-create-grid">
              <label>
                Тип кабинета
                <select
                  value={form.role}
                  onChange={(event) =>
                    updateForm(
                      "role",
                      event.target.value as "doctor" | "patient",
                    )
                  }
                >
                  <option value="patient">Пациент</option>
                  <option value="doctor">Врач</option>
                </select>
              </label>
              <label>
                ФИО
                <input
                  value={form.name}
                  onChange={(event) => updateForm("name", event.target.value)}
                  placeholder="Иванов Иван Иванович"
                />
              </label>
              <label>
                Логин
                <input
                  value={form.login}
                  onChange={(event) => updateForm("login", event.target.value)}
                  placeholder="ivanov.i"
                  autoComplete="off"
                />
              </label>
              <label>
                Временный пароль
                <input
                  type="password"
                  value={form.password}
                  onChange={(event) =>
                    updateForm("password", event.target.value)
                  }
                  placeholder="Не короче 8 символов"
                  autoComplete="new-password"
                />
              </label>
              <label>
                Электронная почта
                <input
                  type="email"
                  value={form.email}
                  onChange={(event) => updateForm("email", event.target.value)}
                  placeholder="name@example.ru"
                />
              </label>
              <label>
                Телефон
                <input
                  value={form.phone}
                  onChange={(event) => updateForm("phone", event.target.value)}
                  placeholder="+7 999 000-00-00"
                />
              </label>
              {form.role === "doctor" ? (
                <>
                  <label>
                    Специальность
                    <input
                      value={form.specialty}
                      onChange={(event) =>
                        updateForm("specialty", event.target.value)
                      }
                      placeholder="Врач-психиатр"
                    />
                  </label>
                  <label>
                    Организация
                    <input
                      value={form.organization}
                      onChange={(event) =>
                        updateForm("organization", event.target.value)
                      }
                      placeholder="Название клиники"
                    />
                  </label>
                </>
              ) : (
                <>
                  <label>
                    Возраст
                    <input
                      type="number"
                      min={18}
                      max={120}
                      value={form.patientAge ?? ""}
                      onChange={(event) =>
                        updateForm(
                          "patientAge",
                          event.target.value
                            ? Number(event.target.value)
                            : null,
                        )
                      }
                      placeholder="Возраст"
                    />
                  </label>
                  <label>
                    Пол
                    <select
                      value={form.patientSex}
                      onChange={(event) =>
                        updateForm(
                          "patientSex",
                          event.target.value as "Ж" | "М",
                        )
                      }
                    >
                      <option value="Ж">Женский</option>
                      <option value="М">Мужской</option>
                    </select>
                  </label>
                  <label>
                    Код диагноза
                    <input
                      value={form.diagnosisCode}
                      onChange={(event) =>
                        updateForm("diagnosisCode", event.target.value)
                      }
                      placeholder="Например, F41.1"
                    />
                  </label>
                  <label>
                    Лечащий врач
                    <select
                      value={form.doctorId}
                      onChange={(event) =>
                        updateForm("doctorId", event.target.value)
                      }
                    >
                      <option value="">Выберите врача</option>
                      {doctors.map((doctor) => (
                        <option key={doctor.id} value={doctor.id}>
                          {doctor.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              )}
            </div>
            <InfoNote>
              {form.role === "patient"
                ? "После создания пациента система автоматически выдаст одноразовый код для привязки MAX. Код действует 24 часа."
                : "ФИО, специальность и организацию врача позднее сможет изменить только администратор."}
            </InfoNote>
            <button
              className="primary account-create-submit"
              disabled={busy === "create"}
              onClick={requestCreate}
            >
              {busy === "create" ? (
                <LoaderCircle className="spin" size={18} />
              ) : (
                <UserPlus size={18} />
              )}
              Создать учётную запись
            </button>
          </div>
        )}

        {maxLink && (
          <div className="max-code-panel">
            <span className="max-code-icon">
              <KeyRound size={23} />
            </span>
            <div>
              <small>Код привязки к MAX для {maxLink.patientName}</small>
              <strong>{maxLink.value.code}</strong>
              <p>
                Действует до{" "}
                {new Date(maxLink.value.expiresAt).toLocaleString("ru-RU")}. Код
                показывается после выпуска — передайте его пациенту безопасным
                способом.
              </p>
            </div>
            <button className="outline" onClick={copyCode}>
              <Copy size={17} />
              Копировать
            </button>
            <button
              className="icon-button"
              aria-label="Скрыть код"
              onClick={() => setMaxLink(null)}
            >
              <X />
            </button>
          </div>
        )}

        <div className="account-count">
          <span>{accounts.length} учётных записей</span>
        </div>
        <div className="account-list">
          {accounts.map((account) => (
            <article
              className={`account-row ${account.role === "doctor" ? "doctor-account" : ""}`}
              key={account.id}
            >
              <div className="account-row-main">
                <div className="account-person">
                  <span className="doctor-avatar">
                    {account.name
                      .split(" ")
                      .map((part) => part[0])
                      .join("")
                      .slice(0, 2)}
                  </span>
                  <span>
                    <strong>{account.name}</strong>
                    <small>
                      {account.login} · {account.email || "почта не указана"} ·{" "}
                      {account.phone || "телефон не указан"}
                    </small>
                  </span>
                </div>
                {account.role === "admin" ? (
                  <span className="badge green">Администратор</span>
                ) : (
                  <div className="account-actions">
                    {account.role === "patient" && (
                      <button
                        className="outline compact"
                        disabled={busy === account.id}
                        onClick={() => requestMaxCode(account)}
                      >
                        <RefreshCw size={15} />
                        Код MAX на 24 часа
                      </button>
                    )}
                    <label className="account-role">
                      <span>Кабинет</span>
                      <select
                        aria-label={`Роль пользователя ${account.name}`}
                        value={account.role}
                        disabled={busy === account.id}
                        onChange={(event) =>
                          requestRoleChange(
                            account,
                            event.target.value as "doctor" | "patient",
                          )
                        }
                      >
                        <option value="doctor">Врач</option>
                        <option value="patient">Пациент</option>
                      </select>
                    </label>
                  </div>
                )}
              </div>
              {account.role === "doctor" && (
                <div className="admin-profile-form">
                  <label>
                    ФИО
                    <input
                      value={account.name}
                      onChange={(event) =>
                        updateAccountDraft(
                          account.id,
                          "name",
                          event.target.value,
                        )
                      }
                    />
                  </label>
                  <label>
                    Специальность
                    <input
                      value={account.specialty || ""}
                      onChange={(event) =>
                        updateAccountDraft(
                          account.id,
                          "specialty",
                          event.target.value,
                        )
                      }
                    />
                  </label>
                  <label>
                    Организация
                    <input
                      value={account.organization || ""}
                      onChange={(event) =>
                        updateAccountDraft(
                          account.id,
                          "organization",
                          event.target.value,
                        )
                      }
                    />
                  </label>
                  <button
                    className="primary"
                    disabled={busy === account.id}
                    onClick={() => requestProfileSave(account)}
                  >
                    Сохранить профиль врача
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
        <InfoNote>
          Профессиональный профиль врача меняет администратор. Врач
          самостоятельно управляет только привязанными почтой и телефоном.
        </InfoNote>
      </section>

      {confirmation && (
        <div
          className="modal-backdrop confirmation-backdrop"
          role="presentation"
        >
          <section
            className="modal confirmation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirmation-title"
          >
            <span className="confirmation-icon">
              <ShieldCheck size={25} />
            </span>
            <h2 id="confirmation-title">{confirmation.title}</h2>
            <p>{confirmation.text}</p>
            <div className="modal-actions">
              <button className="outline" onClick={() => setConfirmation(null)}>
                Отмена
              </button>
              <button className="primary" onClick={runConfirmed}>
                {confirmation.confirmLabel}
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
