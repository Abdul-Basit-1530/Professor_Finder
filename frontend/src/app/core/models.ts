export type Verification = 'VERIFIED' | 'PARTIALLY VERIFIED' | 'NOT VERIFIED' | 'NOT FOUND';
export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface FieldOption {
  key: string;
  label: string;
  label_zh: string | null;
  custom: boolean;
}

export interface PublicConfig {
  default_fields: FieldOption[];
  llm_enabled: boolean;
  llm_model: string | null;
  search_provider: string;
  max_professors: number;
  access_token_required: boolean;
}

export interface ResearchStartRequest {
  university_url: string;
  fields: string[];
  custom_fields: string[];
  max_professors?: number | null;
  force_refresh: boolean;
}

export interface Step {
  key: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped';
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Job {
  id: string;
  university_url: string;
  university_name: string | null;
  fields: string[];
  options: { max_professors?: number; force_refresh?: boolean };
  status: JobStatus;
  progress: number;
  current_step: string | null;
  steps: Step[];
  warnings: string[];
  stats: Record<string, unknown>;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface Source {
  id: number;
  entity_type: string;
  entity_id: number | null;
  supports: string | null;
  source_url: string;
  source_type: string;
  title: string | null;
  retrieved_at: string;
}

export interface University {
  id: number | null;
  name: string | null;
  name_chinese: string | null;
  official_url: string;
  domain: string;
  country: string | null;
  location: string | null;
  verification_status: Verification;
  sources: Source[];
}

export interface Department {
  id: number;
  name: string;
  name_chinese: string | null;
  school: string | null;
  url: string | null;
  faculty_list_urls: string[];
  matched_fields: string[];
  relevance_score: number;
  verification_status: Verification;
}

export interface Professor {
  id: number;
  job_id: string;
  name: string;
  name_chinese: string | null;
  name_is_romanized: boolean;
  position: string | null;
  position_original: string | null;
  department_id: number | null;
  department_name: string | null;
  school: string | null;
  email: string | null;
  email_verified: boolean;
  email_status: string;
  profile_url: string | null;
  verification_status: Verification;
}

export interface ProfessorDetail extends Professor {
  verification_checks: Record<string, boolean>;
  notes: string[];
  sources: Source[];
  university_name: string | null;
}

export interface EmailRequest {
  student_name: string;
  student_background: string;
  target_degree: string;
  research_interest: string;
  scholarship: string;
  extra_notes?: string | null;
  tone: 'formal' | 'warm' | 'concise';
}

export interface EmailDraft {
  id: number;
  professor_id: number;
  subject: string;
  body: string;
  generated_by: 'llm' | 'template';
  warnings: string[];
  created_at: string;
}
