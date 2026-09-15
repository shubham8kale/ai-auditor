export type Payload = Record<string, any>;
export interface Config {
  supabase_url: string;
  publishable_key: string;
  local_auth: boolean;
  ai_configured: boolean;
  max_upload_mb: number;
}
export interface Engagement {
  id: string;
  name: string;
  period_end: string;
  version: number;
  profile: Payload;
  overrides: Payload;
}
export interface Finding {
  code: string;
  severity: string;
  message: string;
  source?: string;
  document_id?: string;
}
export interface Evidence {
  id: string;
  filename: string;
  kind: string;
  status: string;
  size: number;
  findings: Finding[];
  extracted?: Payload;
  reviewed_by?: string;
  reviewed_at?: string;
}
export interface Revision {
  id: string;
  stage: string;
  status: string;
  payload: Payload;
  created_at: string;
  prepared_by: string;
  approved_by?: string;
  approved_at?: string;
  stale_reason?: string;
}
export interface Job {
  id: string;
  stage: string;
  status: string;
  message: string;
  detail: Payload;
}
export interface PbcRequest {
  id: string;
  title: string;
  kind: string;
  status: string;
  why: string;
  source: string;
  document_ids: string[];
}
export interface Message {
  id: string;
  role: string;
  content: string;
  detail: Payload;
}
export interface AuditEvent {
  id: string;
  actor: string;
  action: string;
  detail: Payload;
  created_at: string;
}
export interface Workspace {
  engagement: Engagement;
  documents: Evidence[];
  revisions: Revision[];
  requests: PbcRequest[];
  jobs: Job[];
  messages: Message[];
  events: AuditEvent[];
}
