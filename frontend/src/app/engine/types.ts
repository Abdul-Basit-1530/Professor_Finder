export type Verification = 'VERIFIED' | 'PARTIALLY VERIFIED' | 'NOT VERIFIED';
export type StepStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped';

export interface SourceRef {
  url: string;
  title: string | null;
  supports: string; // e.g. "profile", "listed_on_faculty_page", "department"
}

export interface UniversityInfo {
  officialUrl: string;
  domain: string;
  name: string | null;
  nameChinese: string | null;
  location: string | null;
  verified: boolean;
  sources: SourceRef[];
}

export interface DepartmentInfo {
  name: string;
  nameChinese: string | null;
  url: string;
  facultyListUrls: string[];
  matchedFields: string[];
  relevance: number;
}

export interface ProfessorInfo {
  id: number;
  name: string;
  nameChinese: string | null;
  nameIsRomanized: boolean;
  position: string | null;
  positionOriginal: string | null;
  department: string | null;
  email: string | null;
  emailVerified: boolean;
  profileUrl: string | null;
  listingUrl: string | null;
  profileOk: boolean;
  verification: Verification;
  checks: Record<string, boolean>;
  notes: string[];
  sources: SourceRef[];
  /** in-memory only, used for verification; never persisted */
  profileText: string;
  profileMailtos: string[];
}

export interface Step {
  key: 'university' | 'departments' | 'professors' | 'verification';
  label: string;
  status: StepStatus;
  message: string | null;
}

export interface ResearchResult {
  university: UniversityInfo | null;
  departments: DepartmentInfo[];
  professors: ProfessorInfo[];
  warnings: string[];
  pagesFetched: number;
  error: string | null;
}
