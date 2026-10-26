import type { ClinicalRepository } from "../repositories";
import type {
  MedicationReview,
  Account,
  AdminAccountCreateResult,
  AdminAccountInput,
  AlertUpdate,
  AppData,
  AiRecommendation,
  AiRequest,
  AiStatus,
  AuthSession,
  ClinicalAlert,
  ClinicalTask,
  MaxLinkCode,
  MessageConversation,
  PatientMessage,
  Patient,
  PatientInput,
  QuestionnaireAssignment,
  QuestionnaireAssignmentInput,
  QuestionnaireTemplate,
  QuestionnaireTemplateInput,
  QuestionnaireVersion,
  QuestionnaireVersionInput,
  Settings,
} from "../types";
export class ApiClinicalRepository implements ClinicalRepository {
  getMedicationReview(patientId: string) {
    return this.request<MedicationReview>(`/patients/${encodeURIComponent(patientId)}/medication-review`);
  }
  saveMedicationReview(patientId: string, review: MedicationReview) {
    return this.request<MedicationReview>(`/patients/${encodeURIComponent(patientId)}/medication-review`, "PUT", { ...review, confirmed: true });
  }
  constructor(private baseUrl: string) {}
  private async request<T>(
    path: string,
    method = "GET",
    body?: unknown,
  ): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method,
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!res.ok) {
      let detail = "";
      try {
        const payload = (await res.json()) as { detail?: unknown };
        detail = typeof payload.detail === "string" ? payload.detail : Array.isArray(payload.detail) ? payload.detail.map((item: { msg?: string }) => item.msg || "Некорректное значение").join("; ") : "";
      } catch {}
      throw new Error(
        detail ||
          (res.status === 403 || res.status === 401
            ? "Нет доступа. Войдите снова."
            : `API недоступен (${res.status}). Проверьте подключение FastAPI.`),
      );
    }
    return res.status === 204 ? (undefined as T) : (res.json() as Promise<T>);
  }
  login(login: string, password: string) {
    return this.request<AuthSession>("/auth/login", "POST", {
      login,
      password,
    });
  }
  logout() { return this.request<void>("/auth/logout", "POST"); }
  refresh() {
    return this.request<void>("/auth/refresh", "POST");
  }
  getUsers() {
    return this.request<Account[]>("/admin/users");
  }
  createUser(input: AdminAccountInput) {
    return this.request<AdminAccountCreateResult>(
      "/admin/users",
      "POST",
      input,
    );
  }
  updateUserRole(id: string, role: "doctor" | "patient") {
    return this.request<Account>(
      `/admin/users/${encodeURIComponent(id)}/role`,
      "PATCH",
      { role },
    );
  }
  updateUserProfile(
    id: string,
    profile: Pick<Settings, "name" | "specialty" | "organization">,
  ) {
    return this.request<Account>(
      `/admin/users/${encodeURIComponent(id)}/profile`,
      "PATCH",
      profile,
    );
  }
  createMaxLinkCode(patientId: string) {
    return this.request<MaxLinkCode>(
      `/patients/${encodeURIComponent(patientId)}/max/link-code`,
      "POST",
      { expiresInMinutes: 1440 },
    );
  }
  createOwnMaxLinkCode() {
    return this.request<MaxLinkCode>("/account/max/link-code", "POST");
  }
  getAccount() {
    return this.request<Account>("/account");
  }
  saveContact(email: string, phone: string) {
    return this.request<Account>("/account/contact", "PATCH", { email, phone });
  }
  getMessageConversations() {
    return this.request<MessageConversation[]>("/messages");
  }
  getPatientMessages(patientId: string) {
    return this.request<PatientMessage[]>(
      `/messages/${encodeURIComponent(patientId)}`,
    );
  }
  sendPatientMessage(patientId: string, text: string) {
    return this.request<PatientMessage>(
      `/messages/${encodeURIComponent(patientId)}`,
      "POST",
      { text },
    );
  }
  getData() {
    return this.request<AppData>("/dashboard");
  }
  getPatients() {
    return this.request<Patient[]>("/patients");
  }
  getPatient(id: string) {
    return this.request<Patient>(`/patients/${encodeURIComponent(id)}`);
  }
  addPatient(input: PatientInput) {
    return this.request<Patient>("/patients", "POST", input);
  }
  getDynamics(id: string) {
    return this.request<Patient["dynamics"]>(
      `/patients/${encodeURIComponent(id)}/dynamics`,
    );
  }
  getPrescriptions(id: string) {
    return this.request<Patient["prescriptions"]>(
      `/patients/${encodeURIComponent(id)}/prescriptions`,
    );
  }
  getQuestionnaires(id: string) {
    return this.request<Patient["questionnaires"]>(
      `/patients/${encodeURIComponent(id)}/questionnaires`,
    );
  }
  getPatientAlerts(id: string) {
    return this.request<ClinicalAlert[]>(
      `/patients/${encodeURIComponent(id)}/alerts`,
    );
  }
  getAlerts() {
    return this.request<ClinicalAlert[]>("/alerts");
  }
  updateAlert(id: string, update: AlertUpdate) {
    return this.request<ClinicalAlert>(
      `/alerts/${encodeURIComponent(id)}`,
      "PATCH",
      update,
    );
  }
  addTask(task: Omit<ClinicalTask, "id" | "status">) {
    return this.request<ClinicalTask>(
      `/patients/${encodeURIComponent(task.patientId)}/tasks`,
      "POST",
      task,
    );
  }
  updateTask(id: string, status: ClinicalTask["status"]) {
    return this.request<void>(`/tasks/${encodeURIComponent(id)}`, "PATCH", {
      status,
    });
  }
  getQuestionnaireLibrary() {
    return this.request<QuestionnaireTemplate[]>("/questionnaire-library");
  }
  createQuestionnaireTemplate(input: QuestionnaireTemplateInput) {
    return this.request<QuestionnaireTemplate>(
      "/admin/questionnaire-library",
      "POST",
      input,
    );
  }
  createQuestionnaireVersion(
    templateId: string,
    input: QuestionnaireVersionInput,
  ) {
    return this.request<QuestionnaireVersion>(
      `/admin/questionnaire-library/${encodeURIComponent(templateId)}/versions`,
      "POST",
      input,
    );
  }
  publishQuestionnaireVersion(versionId: string) {
    return this.request<QuestionnaireTemplate>(
      `/admin/questionnaire-library/versions/${encodeURIComponent(versionId)}/publish`,
      "POST",
      { confirmed: true },
    );
  }
  archiveQuestionnaireVersion(versionId: string) {
    return this.request<QuestionnaireTemplate>(
      `/admin/questionnaire-library/versions/${encodeURIComponent(versionId)}/archive`,
      "POST",
      { confirmed: true },
    );
  }
  assignQuestionnaire(patientId: string, input: QuestionnaireAssignmentInput) {
    return this.request<QuestionnaireAssignment>(
      `/patients/${encodeURIComponent(patientId)}/questionnaires`,
      "POST",
      input,
    );
  }
  generateAi(request: AiRequest) {
    return this.request<AiRecommendation>(
      request.kind === "summary" ? "/ai/summary" : "/ai/recommendation",
      "POST",
      request,
    );
  }
  getAiStatus() {
    return this.request<AiStatus>("/ai/status");
  }
  updateAi(
    id: string,
    text: string,
    status: AiRecommendation["status"],
    confirmed: boolean,
  ) {
    return this.request<void>(
      `/ai/recommendations/${encodeURIComponent(id)}`,
      "PATCH",
      { text, status, confirmed },
    );
  }
  getDocuments() {
    return this.request<AppData["documents"]>("/clinical-documents");
  }
  getAudit() {
    return this.request<AppData["audit"]>("/audit");
  }
  saveSettings(settings: Settings) {
    return this.request<void>("/settings", "PATCH", settings);
  }
  async reset() {
    throw new Error("Сброс доступен только для локального хранилища");
  }
}
