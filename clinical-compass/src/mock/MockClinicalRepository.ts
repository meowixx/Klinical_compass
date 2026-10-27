import type { ClinicalRepository } from "../repositories";
import type {
  Account,
  AdminAccountInput,
  AlertUpdate,
  AppData,
  AiRecommendation,
  AiRequest,
  AiStatus,
  ClinicalTask,
  MessageConversation,
  PatientMessage,
  Patient,
  PatientInput,
  QuestionnaireAssignmentInput,
  QuestionnaireTemplate,
  QuestionnaireTemplateInput,
  QuestionnaireVersionInput,
  Settings,
} from "../types";
import { createSeed } from "./seed";
import { patientSchema, validateAlertUpdate } from "../services/validation";
export interface StorageAdapter {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}
const KEY = "clinical-compass-data-v2";
export class MockClinicalRepository implements ClinicalRepository {
  async getMedicationReview(): Promise<MedicationReview> {
    return { diagnosisConfirmed: false, firstTwoLinesRefractory: false, contraindicationsReviewed: false, restrictions: "" };
  }
  async saveMedicationReview(): Promise<MedicationReview> {
    throw new Error("Сохранение проверки врача требует подключения FastAPI.");
  }
  async logout() {}
  private data: AppData | null = null;
  private messages: PatientMessage[] = [];
  private library: QuestionnaireTemplate[] = [
    {
      id: "template-daily-checkin",
      code: "DAILY-CHECKIN",
      title: "Ежедневный дневник состояния",
      description: "Короткий авторский дневник для наблюдения между визитами.",
      category: "Дневник",
      sourceUrl: "",
      kind: "diary",
      status: "published",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      publishedVersion: {
        id: "version-daily-checkin-1",
        templateId: "template-daily-checkin",
        version: "1.0",
        instructions: "Отвечайте исходя из состояния сегодня.",
        status: "published",
        requiresClinicalApproval: false,
        approvedByUserId: null,
        createdAt: new Date().toISOString(),
        publishedAt: new Date().toISOString(),
        questions: [
          {
            id: "wellbeing",
            text: "Как вы оцениваете общее самочувствие сегодня?",
            type: "number",
            required: true,
            options: [],
            min: 0,
            max: 10,
          },
        ],
        scoring: {},
        alertRules: [],
      },
      versions: [],
    },
  ];
  private accounts: (Account & { hash: string })[] = [
    {
      id: "admin-demo",
      login: "Admin",
      email: "admin@clinical-compass.local",
      phone: "+79990000001",
      name: "Администратор",
      role: "admin",
      specialty: null,
      organization: null,
      patientId: null,
      hash: "8ace459c5a5c47a6931cf66dedf0dbdcd02a8d8d37fee7026d5fbf444f8dae4b",
    },
    {
      id: "doctor-demo",
      login: "Persent",
      email: "doctor@clinical-compass.local",
      phone: "+79990000002",
      name: "Елена Смирнова",
      role: "doctor",
      specialty: "Врач-невролог",
      organization: "Клиника «Гармония»",
      patientId: null,
      hash: "d006b3f546ac914c34dfc209ad535ea530f32a1e8e0ae822ea049b3a783e4d20",
    },
    {
      id: "patient-demo",
      login: "Doctor",
      email: "patient@clinical-compass.local",
      phone: "+79990000003",
      name: "Анна К.",
      role: "patient",
      specialty: null,
      organization: null,
      patientId: "p1",
      hash: "af26c1520c5e2e97ecc6b3b2e3f6064dd7db1e0abe35239240bc631c6fc005f3",
    },
  ];
  constructor(private storage?: StorageAdapter) {}
  private accountView(account: Account & { hash: string }): Account {
    return {
      id: account.id,
      login: account.login,
      email: account.email,
      phone: account.phone,
      name: account.name,
      role: account.role,
      specialty: account.specialty,
      organization: account.organization,
      patientId: account.patientId,
    };
  }
  private read(): AppData {
    if (!this.data) {
      const saved = this.storage?.getItem(KEY);
      if (saved) {
        try {
          const parsed = JSON.parse(saved) as AppData;
          if (
            !Array.isArray(parsed.patients) ||
            !parsed.settings ||
            !Array.isArray(parsed.audit)
          )
            throw new Error();
          this.data = parsed;
        } catch {
          throw new Error(
            "Не удалось прочитать сохранённые данные. Сбросьте их кнопкой ниже.",
          );
        }
      } else this.data = createSeed();
    }
    return this.data;
  }
  private write(data: AppData) {
    this.storage?.setItem(KEY, JSON.stringify(data));
    this.data = data;
  }
  private mutate<T>(fn: (data: AppData) => T): T {
    const next = structuredClone(this.read());
    const result = fn(next);
    this.write(next);
    return structuredClone(result);
  }
  private audit(data: AppData, action: string, entityId: string) {
    data.audit.unshift({
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      actor: data.settings.name,
      action,
      entityId,
    });
  }
  async login(login: string, password: string) {
    const digest = Array.from(
      new Uint8Array(
        await crypto.subtle.digest(
          "SHA-256",
          new TextEncoder().encode(password),
        ),
      ),
    )
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    const identifier = login.trim().toLowerCase();
    const phone = `+${login.replace(/\D/g, "").replace(/^8(?=\d{10}$)/, "7")}`;
    const account = this.accounts.find(
      (item) =>
        item.login.toLowerCase() === identifier ||
        item.email?.toLowerCase() === identifier ||
        item.phone === phone,
    );
    if (!account || digest !== account.hash)
      throw new Error("Неверный логин, почта, телефон или пароль.");
    return {
      user: { id: account.id, name: account.name, role: account.role },
      issuedAt: new Date().toISOString(),
    };
  }
  async refresh() {}
  async getUsers() {
    return this.accounts.map((account) =>
      structuredClone(this.accountView(account)),
    );
  }
  async createUser(input: AdminAccountInput) {
    const id = crypto.randomUUID();
    const patientId = input.role === "patient" ? crypto.randomUUID() : null;
    const account = {
      id,
      login: input.login,
      email: input.email || null,
      phone: input.phone || null,
      name: input.name,
      role: input.role,
      specialty: input.role === "doctor" ? input.specialty : null,
      organization: input.role === "doctor" ? input.organization : null,
      patientId,
      hash: "",
    } as Account & { hash: string };
    this.accounts.push(account);
    return {
      account: this.accountView(account),
      maxLink: patientId
        ? {
            code: crypto.randomUUID().replaceAll("-", "").slice(0, 12),
            expiresAt: new Date(Date.now() + 86400000).toISOString(),
            instruction: "Отправьте этот код боту MAX",
          }
        : null,
    };
  }
  async updateUserRole(id: string, role: "doctor" | "patient") {
    const account = this.accounts.find((item) => item.id === id);
    if (!account) throw new Error("Учётная запись не найдена");
    if (account.role === "admin")
      throw new Error("Роль администратора нельзя изменить здесь");
    account.role = role;
    return structuredClone(this.accountView(account));
  }
  async updateUserProfile(
    id: string,
    profile: Pick<Settings, "name" | "specialty" | "organization">,
  ) {
    const account = this.accounts.find((item) => item.id === id);
    if (!account || account.role !== "doctor")
      throw new Error("Профессиональный профиль доступен только врачу");
    Object.assign(account, profile);
    return structuredClone(this.accountView(account));
  }
  async createMaxLinkCode(patientId: string) {
    if (!patientId) throw new Error("Карточка пациента не найдена");
    return {
      code: crypto.randomUUID().replaceAll("-", "").slice(0, 12),
      expiresAt: new Date(Date.now() + 86400000).toISOString(),
      instruction: "Отправьте этот код боту MAX",
    };
  }
  async createOwnMaxLinkCode() {
    return {
      code: crypto.randomUUID().replaceAll("-", "").slice(0, 12),
      expiresAt: new Date(Date.now() + 86400000).toISOString(),
      instruction: "Отправьте этот код боту MAX",
    };
  }
  async getAccount() {
    const account = this.accounts.find((item) => item.id === "doctor-demo");
    if (!account) throw new Error("Учётная запись не найдена");
    return structuredClone(this.accountView(account));
  }
  async saveContact(email: string, phone: string) {
    const account = this.accounts.find((item) => item.id === "doctor-demo");
    if (!account) throw new Error("Учётная запись не найдена");
    account.email = email.trim().toLowerCase();
    account.phone = phone;
    return structuredClone(this.accountView(account));
  }
  async getMessageConversations(): Promise<MessageConversation[]> {
    return this.read().patients.map((patient) => {
      const messages = this.messages.filter((item) => item.patientId === patient.id);
      return {
        patientId: patient.id,
        patientName: patient.name,
        card: patient.card,
        maxConnected: patient.id === "p1",
        unreadCount: messages.filter((item) => item.senderRole === "patient" && !item.readAt).length,
        lastMessage: messages.at(-1) || null,
      };
    });
  }
  async getPatientMessages(patientId: string): Promise<PatientMessage[]> {
    const now = new Date().toISOString();
    this.messages.forEach((item) => {
      if (item.patientId === patientId && item.senderRole === "patient" && !item.readAt) item.readAt = now;
    });
    return structuredClone(this.messages.filter((item) => item.patientId === patientId));
  }
  async sendPatientMessage(patientId: string, text: string): Promise<PatientMessage> {
    const item: PatientMessage = {
      id: crypto.randomUUID(), patientId, senderRole: "doctor", text: text.trim(), source: "site",
      createdAt: new Date().toISOString(), readAt: null, deliveredAt: new Date().toISOString(),
    };
    this.messages.push(item);
    return structuredClone(item);
  }
  async getData() {
    return structuredClone(this.read());
  }
  async getPatients() {
    return (await this.getData()).patients;
  }
  async getPatient(id: string) {
    const p = this.read().patients.find((p) => p.id === id);
    if (!p) throw new Error("Пациент не найден");
    return structuredClone(p);
  }
  async addPatient(input: PatientInput) {
    const value = patientSchema.parse(input);
    return this.mutate((data) => {
      const p: Patient = {
        ...value,
        id: crypto.randomUUID(),
        card: `КК-${Date.now().toString().slice(-6)}`,
        doctor: data.settings.name,
        status: "active",
        risk: "green",
        adherence: 0,
        color: "#e2eaff",
        diagnosis: { code: value.code, title: "Код требует проверки врача" },
        lastContact: new Date().toISOString(),
        complaint: "Данные ещё не получены",
        dynamics: [],
        questionnaires: [],
        prescriptions: [],
      };
      data.patients.push(p);
      this.audit(data, "Добавлен пациент", p.id);
      return p;
    });
  }
  async updateAlert(id: string, update: AlertUpdate) {
    return this.mutate((data) => {
      const a = data.alerts.find((a) => a.id === id);
      if (!a) throw new Error("Алерт не найден");
      validateAlertUpdate(a, update);
      Object.assign(a, update, {
        comment: update.comment.trim(),
        action: update.action.trim(),
        reviewedAt: new Date().toISOString(),
      });
      this.audit(
        data,
        `${update.status === "closed" ? "Закрыт алерт" : update.status === "working" ? "Алерт принят в работу" : "Алерт обновлён"}: ${a.reason}. ${update.comment}`,
        id,
      );
      return a;
    });
  }
  async addTask(input: Omit<ClinicalTask, "id" | "status">) {
    return this.mutate((data) => {
      if (!data.patients.some((p) => p.id === input.patientId))
        throw new Error("Выберите пациента");
      if (!input.title.trim() || !input.dueAt)
        throw new Error("Заполните название и срок");
      const task: ClinicalTask = {
        ...input,
        id: crypto.randomUUID(),
        status: "new",
      };
      data.tasks.push(task);
      this.audit(data, `Создана задача: ${task.title}`, task.patientId);
      return task;
    });
  }
  async updateTask(id: string, status: ClinicalTask["status"]) {
    this.mutate((data) => {
      const t = data.tasks.find((t) => t.id === id);
      if (!t) throw new Error("Задача не найдена");
      t.status = status;
      this.audit(data, `Статус задачи «${t.title}»: ${status}`, id);
      return true;
    });
  }
  async getQuestionnaireLibrary() {
    return structuredClone(this.library);
  }
  async createQuestionnaireTemplate(input: QuestionnaireTemplateInput) {
    const now = new Date().toISOString();
    if (
      this.library.some(
        (item) => item.code.toLowerCase() === input.code.toLowerCase(),
      )
    )
      throw new Error("Код опросника уже используется");
    const version = {
      id: crypto.randomUUID(),
      templateId: "",
      version: input.version,
      instructions: input.instructions,
      status: "draft" as const,
      requiresClinicalApproval:
        input.requiresClinicalApproval || input.kind === "validated",
      approvedByUserId: null,
      createdAt: now,
      publishedAt: null,
      questions: input.questions,
      scoring: input.scoring,
      alertRules: input.alertRules,
    };
    const template: QuestionnaireTemplate = {
      id: crypto.randomUUID(),
      code: input.code,
      title: input.title,
      description: input.description,
      category: input.category,
      sourceUrl: input.sourceUrl,
      kind: input.kind,
      status: "draft",
      createdAt: now,
      updatedAt: now,
      publishedVersion: null,
      versions: [],
    };
    version.templateId = template.id;
    template.versions = [version];
    this.library.push(template);
    return structuredClone(template);
  }
  async createQuestionnaireVersion(
    templateId: string,
    input: QuestionnaireVersionInput,
  ) {
    const template = this.library.find((item) => item.id === templateId);
    if (!template) throw new Error("Опросник не найден");
    if (template.versions.some((item) => item.version === input.version))
      throw new Error("Такая версия уже существует");
    const version = {
      id: crypto.randomUUID(),
      templateId,
      version: input.version,
      instructions: input.instructions,
      status: "draft" as const,
      requiresClinicalApproval:
        input.requiresClinicalApproval || template.kind === "validated",
      approvedByUserId: null,
      createdAt: new Date().toISOString(),
      publishedAt: null,
      questions: input.questions,
      scoring: input.scoring,
      alertRules: input.alertRules,
    };
    template.versions.unshift(version);
    template.updatedAt = version.createdAt;
    return structuredClone(version);
  }
  async publishQuestionnaireVersion(versionId: string) {
    const template = this.library.find((item) =>
      item.versions.some((version) => version.id === versionId),
    );
    if (!template) throw new Error("Версия не найдена");
    const version = template.versions.find((item) => item.id === versionId)!;
    if (version.requiresClinicalApproval && !version.approvedByUserId)
      throw new Error("Сначала требуется клиническое утверждение врачом");
    template.versions.forEach((item) => {
      if (item.status === "published") item.status = "archived";
    });
    version.status = "published";
    version.publishedAt = new Date().toISOString();
    template.publishedVersion = structuredClone(version);
    template.status = "published";
    return structuredClone(template);
  }
  async archiveQuestionnaireVersion(versionId: string) {
    const template = this.library.find((item) =>
      item.versions.some((version) => version.id === versionId),
    );
    if (!template) throw new Error("Версия не найдена");
    const version = template.versions.find((item) => item.id === versionId)!;
    version.status = "archived";
    if (template.publishedVersion?.id === versionId)
      template.publishedVersion = null;
    if (!template.publishedVersion) template.status = "archived";
    return structuredClone(template);
  }
  async assignQuestionnaire(
    patientId: string,
    input: QuestionnaireAssignmentInput,
  ) {
    return this.mutate((data) => {
      const template = this.library.find(
        (item) => item.publishedVersion?.id === input.versionId,
      );
      if (
        !data.patients.some((p) => p.id === patientId) ||
        !template ||
        !input.dueAt
      )
        throw new Error("Заполните все поля");
      const q = {
        id: crypto.randomUUID(),
        patientId,
        template: template.title,
        versionId: input.versionId,
        dueAt: input.dueAt,
        assignedAt: new Date().toISOString(),
        status: "assigned" as const,
      };
      data.assignments.push(q);
      this.audit(data, `Назначен опросник «${template.title}»`, patientId);
      return q;
    });
  }
  async getAiStatus(): Promise<AiStatus> {
    return {provider:"ollama",model:"qwen3:4b-instruct",available:false,message:"Макет использует проверяемые правила"};
  }
  async generateAi(request: AiRequest) {
    return this.mutate((data) => {
      const p = data.patients.find((p) => p.id === request.patientId);
      if (!p) throw new Error("Выберите пациента");
      const active = data.alerts.filter(
        (a) => a.patientId === p.id && a.status !== "closed",
      );
      const texts: Record<string, string> = {
        summary: `${p.name}, ${p.age} лет. ${p.complaint} Приверженность по отметкам пациента — ${p.adherence}%. ${active.length ? "Есть сигналы, ожидающие оценки врача." : "Активных сигналов нет."} Черновик для обсуждения на следующем визите.`,
        changes:
          "Система сравнивает последние записи дневника. Проверьте графики, полноту ответов и обстоятельства изменения самочувствия.",
        risks:
          "Для проверки выделены пропуски отметок терапии и изменение самооценки. Эти признаки требуют проверки врачом; автоматическая оценка клинического риска не выполняется.",
        sources:
          "Для проверки сведений предусмотрены ссылки на каталоги Минздрава России и ГРЛС. Поиск по реальным документам не выполнялся.",
        medication:
          "Карточка препарата партнёра ещё не настроена. До загрузки официальной инструкции препарат не включается в рекомендации. Партнёрский статус не влияет на медицинские критерии.",
        note: `Черновик записи: ${p.name}. Изучены данные дневника и отметки терапии. Жалобы: ${p.complaint} Решение и план наблюдения заполняет врач.`,
        questions:
          "Вопросы к визиту: что изменилось в самочувствии? Как изменился сон? С чем связаны пропуски отметок? Были ли нежелательные явления?",
      };
      const result: AiRecommendation = {
        id: crypto.randomUUID(),
        patientId: p.id,
        kind: request.kind,
        text: texts[request.kind] || texts.summary,
        data: `Дневник: ${p.dynamics.length} записей; опросники: ${p.questionnaires.length}; приверженность: ${p.adherence}%.`,
        risks:
          active.map((a) => a.reason).join("; ") || "Активных сигналов нет.",
        limitations:
          "Заранее подготовленный ответ. Внешняя LLM не подключена. Источники — справочные карточки, актуальность медицинских сведений не проверена.",
        sourceIds: ["doc1", "doc2"],
        createdAt: new Date().toISOString(),
        status: "draft",
      };
      data.recommendations.unshift(result);
      this.audit(data, "Сформирован ответ ИИ-консилиума", p.id);
      return result;
    });
  }
  async updateAi(
    id: string,
    text: string,
    status: AiRecommendation["status"],
    confirmed: boolean,
  ) {
    if (status === "accepted" && !confirmed)
      throw new Error("Необходимо подтверждение врача");
    if (!text.trim()) throw new Error("Черновик не может быть пустым");
    this.mutate((data) => {
      const r = data.recommendations.find((r) => r.id === id);
      if (!r) throw new Error("Черновик не найден");
      Object.assign(r, { text, status });
      this.audit(
        data,
        `${status === "accepted" ? "Врач проверил ответ ИИ-консилиума" : status === "rejected" ? "Ответ ИИ-консилиума не использован" : "Текст ответа обновлён"}`,
        r.patientId,
      );
      return true;
    });
  }
  async saveSettings(settings: Settings) {
    this.mutate((data) => {
      data.settings = {
        ...data.settings,
        notifications: settings.notifications,
        reminders: settings.reminders,
      };
      this.audit(data, "Обновлены настройки уведомлений", "settings");
      return true;
    });
  }
  async reset() {
    this.storage?.removeItem(KEY);
    this.data = createSeed();
  }
}
import type { MedicationReview } from "../types";
