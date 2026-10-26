export type Risk = "red" | "yellow" | "green";
export type AlertStatus = "new" | "working" | "closed";
export type UserRole = "doctor" | "admin" | "patient";
export interface User {
  id: string;
  name: string;
  role: UserRole;
}
export interface Account extends User {
  login: string;
  email: string | null;
  phone: string | null;
  specialty: string | null;
  organization: string | null;
  patientId: string | null;
}
export interface AdminAccountInput {
  login: string;
  password: string;
  name: string;
  role: "doctor" | "patient";
  email: string;
  phone: string;
  specialty: string;
  organization: string;
  patientAge: number | null;
  patientSex: "Ж" | "М";
  diagnosisCode: string;
  doctorId: string;
}
export interface MaxLinkCode {
  code: string;
  expiresAt: string;
  instruction: string;
}
export interface PatientMessage {
  id: string;
  patientId: string;
  senderRole: "patient" | "doctor";
  text: string;
  source: "max" | "site";
  createdAt: string;
  readAt: string | null;
  deliveredAt: string | null;
}
export interface MessageConversation {
  patientId: string;
  patientName: string;
  card: string;
  maxConnected: boolean;
  unreadCount: number;
  lastMessage: PatientMessage | null;
}
export interface AdminAccountCreateResult {
  account: Account;
  maxLink: MaxLinkCode | null;
}
export interface AuthSession {
  user: User;
  issuedAt: string;
}
export interface Doctor extends User {
  specialty: string;
  organizationId: string;
}
export interface Organization {
  id: string;
  name: string;
}
export interface Diagnosis {
  code: string;
  title: string;
}
export interface Medication {
  id: string;
  name: string;
  form: string;
}
export interface MedicationIntake {
  date: string;
  taken: boolean;
}
export interface AdverseEvent {
  id: string;
  date: string;
  description: string;
  status: string;
}
export interface Prescription {
  id: string;
  medication: Medication;
  regimen: string;
  start: string;
  end: string;
  adherence: number;
  intakes: MedicationIntake[];
  events: AdverseEvent[];
  status: string;
}
export interface DailyCheckin {
  date: string;
  anxiety: number;
  mood: number;
  sleep: number;
  wellbeing: number;
  adherence: number;
}
export interface QuestionnaireOption {
  value: string;
  label: string;
  score?: number | null;
}
export interface QuestionnaireQuestion {
  id: string;
  text: string;
  type: "single" | "multiple" | "number" | "text";
  required: boolean;
  options: QuestionnaireOption[];
  min?: number | null;
  max?: number | null;
}
export interface QuestionnaireVersion {
  id: string;
  templateId: string;
  version: string;
  instructions: string;
  status: "draft" | "published" | "archived";
  requiresClinicalApproval: boolean;
  approvedByUserId: string | null;
  createdAt: string;
  publishedAt: string | null;
  questions: QuestionnaireQuestion[];
  scoring: Record<string, unknown>;
  alertRules: Record<string, unknown>[];
}
export interface QuestionnaireTemplate {
  id: string;
  code: string;
  title: string;
  description: string;
  category: string;
  sourceUrl: string;
  kind: "custom" | "validated" | "diary";
  status: "draft" | "published" | "archived";
  createdAt: string;
  updatedAt: string;
  publishedVersion: QuestionnaireVersion | null;
  versions: QuestionnaireVersion[];
}
export interface QuestionnaireTemplateInput {
  code: string;
  title: string;
  description: string;
  category: string;
  sourceUrl: string;
  kind: QuestionnaireTemplate["kind"];
  version: string;
  instructions: string;
  questions: QuestionnaireQuestion[];
  scoring: Record<string, unknown>;
  alertRules: Record<string, unknown>[];
  requiresClinicalApproval: boolean;
}
export interface QuestionnaireVersionInput {
  version: string;
  instructions: string;
  questions: QuestionnaireQuestion[];
  scoring: Record<string, unknown>;
  alertRules: Record<string, unknown>[];
  requiresClinicalApproval: boolean;
}
export interface QuestionnaireAssignment {
  id: string;
  patientId: string;
  template: string;
  versionId?: string | null;
  assignedAt: string;
  dueAt: string;
  status: "assigned" | "completed";
}
export interface QuestionnaireAssignmentInput {
  versionId: string;
  dueAt: string;
  purpose: string;
  scheduleType: "once" | "daily" | "weekly" | "interval";
  intervalDays?: number | null;
  scheduledTime?: string | null;
  timezone: string;
  endAt?: string | null;
  reminderAfterMinutes?: number | null;
}
export interface QuestionnaireResponse {
  id: string;
  template: string;
  date: string;
  score: number;
  previous: number;
  description: string;
}
export interface Patient {
  id: string;
  name: string;
  age: number;
  sex: "Ж" | "М";
  card: string;
  doctor: string;
  status: "active" | "paused";
  risk: Risk;
  diagnosis: Diagnosis;
  lastContact: string;
  adherence: number;
  complaint: string;
  color: string;
  dynamics: DailyCheckin[];
  questionnaires: QuestionnaireResponse[];
  prescriptions: Prescription[];
}
export interface ClinicalAlert {
  id: string;
  patientId: string;
  level: Risk;
  reason: string;
  source: string;
  createdAt: string;
  deliveredAt: string;
  status: AlertStatus;
  comment: string;
  action: string;
  reviewedAt?: string;
}
export interface ClinicalTask {
  id: string;
  patientId: string;
  title: string;
  dueAt: string;
  status: "new" | "working" | "done" | "cancelled";
}
export interface ClinicalDocument {
  id: string;
  title: string;
  category: string;
  organization: string;
  version: string;
  published: string;
  checked: string;
  code: string;
  medication: string;
  url: string;
  text: string;
}
export interface AiRequest {
  patientId: string;
  kind: string;
}
export interface AiStatus {
  provider: "ollama" | "local_adapter";
  model: string;
  available: boolean;
  message: string;
}
export interface AiRecommendation {
  id: string;
  patientId: string;
  kind: string;
  text: string;
  data: string;
  risks: string;
  limitations: string;
  sourceIds: string[];
  createdAt: string;
  status: "draft" | "accepted" | "rejected";
}
export interface AuditEvent {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  entityId: string;
}
export interface Notification {
  id: string;
  text: string;
  read: boolean;
}
export interface Settings {
  name: string;
  specialty: string;
  organization: string;
  notifications: boolean;
  reminders: boolean;
}
export type QueueStatus = Risk | "gray";
export interface AdherenceSummary {
  planned: number;
  confirmed: number;
  missed: number;
  different: number;
  noData: number;
}
export interface DoctorQueueItem {
  patientId: string;
  patientName: string;
  status: QueueStatus;
  reason: string;
  changeSummary: string;
  tolerability: string;
  adherence: AdherenceSummary;
  lastResponseAt: string;
  overdueActions: number;
  nextContactAt: string | null;
  nextContactKind: string;
  recommendedAction: string;
  responsibleDoctor: string;
  source: string;
  measuredAt: string | null;
}
export interface AppData {
  patients: Patient[];
  doctorQueue?: DoctorQueueItem[];
  alerts: ClinicalAlert[];
  tasks: ClinicalTask[];
  documents: ClinicalDocument[];
  recommendations: AiRecommendation[];
  assignments: QuestionnaireAssignment[];
  audit: AuditEvent[];
  settings: Settings;
}
export type PatientInput = Pick<Patient, "name" | "age" | "sex"> & {
  code: string;
};
export type AlertUpdate = Pick<ClinicalAlert, "status" | "comment" | "action">;
export type Simulation = "normal" | "empty" | "error" | "denied";
export interface MedicationReview {
  diagnosisConfirmed: boolean;
  firstTwoLinesRefractory: boolean;
  contraindicationsReviewed: boolean;
  restrictions: string;
  reviewedAt?: string | null;
}
