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
export interface PatientRepository {
  getPatients(): Promise<Patient[]>;
  getPatient(id: string): Promise<Patient>;
  addPatient(input: PatientInput): Promise<Patient>;
}
export interface ClinicalRepository extends PatientRepository {
  login(login: string, password: string): Promise<AuthSession>;
  logout(): Promise<void>;
  refresh(): Promise<void>;
  getUsers(): Promise<Account[]>;
  createUser(input: AdminAccountInput): Promise<AdminAccountCreateResult>;
  updateUserRole(id: string, role: "doctor" | "patient"): Promise<Account>;
  updateUserProfile(
    id: string,
    profile: Pick<Settings, "name" | "specialty" | "organization">,
  ): Promise<Account>;
  createMaxLinkCode(patientId: string): Promise<MaxLinkCode>;
  createOwnMaxLinkCode(): Promise<MaxLinkCode>;
  getAccount(): Promise<Account>;
  saveContact(email: string, phone: string): Promise<Account>;
  getMessageConversations(): Promise<MessageConversation[]>;
  getPatientMessages(patientId: string): Promise<PatientMessage[]>;
  sendPatientMessage(patientId: string, text: string): Promise<PatientMessage>;
  getData(): Promise<AppData>;
  updateAlert(id: string, update: AlertUpdate): Promise<ClinicalAlert>;
  addTask(task: Omit<ClinicalTask, "id" | "status">): Promise<ClinicalTask>;
  updateTask(id: string, status: ClinicalTask["status"]): Promise<void>;
  getQuestionnaireLibrary(): Promise<QuestionnaireTemplate[]>;
  createQuestionnaireTemplate(
    input: QuestionnaireTemplateInput,
  ): Promise<QuestionnaireTemplate>;
  createQuestionnaireVersion(
    templateId: string,
    input: QuestionnaireVersionInput,
  ): Promise<QuestionnaireVersion>;
  publishQuestionnaireVersion(
    versionId: string,
  ): Promise<QuestionnaireTemplate>;
  archiveQuestionnaireVersion(
    versionId: string,
  ): Promise<QuestionnaireTemplate>;
  assignQuestionnaire(
    patientId: string,
    input: QuestionnaireAssignmentInput,
  ): Promise<QuestionnaireAssignment>;
  generateAi(request: AiRequest): Promise<AiRecommendation>;
  getAiStatus(): Promise<AiStatus>;
  getMedicationReview(patientId: string): Promise<MedicationReview>;
  saveMedicationReview(patientId: string, review: MedicationReview): Promise<MedicationReview>;
  updateAi(
    id: string,
    text: string,
    status: AiRecommendation["status"],
    confirmed: boolean,
  ): Promise<void>;
  saveSettings(settings: Settings): Promise<void>;
  reset(): Promise<void>;
}
