import axios from 'axios';

// Resolve API base URL: reads VITE_API_URL, strips trailing slashes, ensures https in production
export function resolveApiBaseUrl(raw?: string): string {
  const trimmed = raw?.trim();
  if (!trimmed) {
    return '/api/v1';
  }
  let url = trimmed.replace(/\/+$/, '');
  // If only a host was passed without protocol (e.g. Render's property: host -> brandshield-api.onrender.com)
  if (!url.startsWith('http://') && !url.startsWith('https://') && !url.startsWith('/')) {
    url = `https://${url}`;
  }
  if (!url.endsWith('/api/v1')) {
    url = `${url}/api/v1`;
  }
  return url;
}

const API_BASE_URL = resolveApiBaseUrl(import.meta.env.VITE_API_URL as string);

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Interceptor: inject JWT bearer token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('brandshield_token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor: extract meaningful error message
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    let message = error.message;
    if (error.code === 'ERR_NETWORK' || error.message === 'Network Error' || !error.response) {
      message = "Can't reach the server. It may be waking up, try again in a minute.";
    } else if (error.response?.data) {
      const data = error.response.data;
      message = data.detail || data.title || data.message || JSON.stringify(data);
    }
    return Promise.reject(new Error(message));
  }
);

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  role: 'CREATOR' | 'REVIEWER' | 'ADMINISTRATOR';
  workspace_id: string;
  is_active: boolean;
}

export interface DashboardSummary {
  total_submissions: number;
  awaiting_review: number;
  approved: number;
  changes_requested: number;
  state_distribution: Record<string, number>;
  total_findings: number;
  findings_by_category: Record<string, number>;
  findings_by_severity: Record<string, number>;
}

export interface RechartsCategoryBar {
  category: string;
  name: string;
  count: number;
  CRITICAL: number;
  HIGH: number;
  MEDIUM: number;
  LOW: number;
}

export interface RechartsReviewTrendLine {
  date: string;
  approved: number;
  changes_requested: number;
  total_reviews: number;
}

export interface RechartsTriagePie {
  name: string;
  value: number;
  fill: string;
  percentage: number;
}

export interface GovernanceReport {
  workspace_id: string;
  brand_profile_id: string | null;
  total_findings: number;
  category_counts: Record<string, number>;
  severity_counts: Record<string, number>;
  triage_status_counts: Record<string, number>;
  detector_source_counts: Record<string, number>;
  recharts_category_bar: RechartsCategoryBar[];
  recharts_review_trends_line: RechartsReviewTrendLine[];
  recharts_triage_pie: RechartsTriagePie[];
  generated_at: string;
}

export interface SubmissionItem {
  id: string;
  workspace_id: string;
  brand_profile_id: string;
  creator_id: string;
  assigned_reviewer_id?: string | null;
  title: string;
  document_type: string;
  workflow_state: string;
  current_revision_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface FindingItem {
  id: string;
  issue_category: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  confidence_score: number;
  triage_status: string;
  start_offset: number;
  end_offset: number;
  explanation_reason: string;
  suggested_correction?: string | null;
  detector_source: string;
  linked_guideline_id?: string | null;
  linked_fact_id?: string | null;
  evidence_source?: string | null;
  evidence_link?: string | null;
  is_automation_bias_audit: boolean;
}

export interface DocumentRevision {
  id: string;
  submission_id: string;
  revision_number: number;
  parent_revision_id: string | null;
  content_text: string;
  ast_span_map: any[];
  created_by_id: string;
  sha256_content_hash: string;
  diff_summary?: any;
  created_at: string;
}

export interface RevisionDiff {
  submission_id: string;
  base_revision_number: number;
  target_revision_number: number;
  base_hash: string;
  target_hash: string;
  diff_unified: string;
  added_lines_count: number;
  deleted_lines_count: number;
  unchanged_lines_count: number;
}

export interface BrandProfileItem {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  tone_parameters: Record<string, any>;
  banned_terminology_map: Record<string, any>;
  preferred_terminology_map: Record<string, any>;
  messaging_rules: Record<string, any>;
  privacy_gate_config: {
    allow_external_llm: boolean;
    approved_providers: string[];
    retention_days: number;
  };
  is_active: boolean;
  created_at: string;
}

export interface BrandGuidelineItem {
  id: string;
  brand_profile_id: string;
  clause_identifier: string;
  clause_text: string;
  category: string;
  severity: string;
  is_active: boolean;
  created_at: string;
}

export interface ApprovedFactItem {
  id: string;
  workspace_id: string;
  brand_profile_id?: string | null;
  fact_statement: string;
  original_source_url: string;
  evidence_excerpt: string;
  verification_date: string;
  expiry_date: string;
  responsible_owner_id: string;
  is_active: boolean;
  created_at: string;
}

export interface AuditLogItem {
  sequence_id: number;
  workspace_id: string;
  actor_id?: string | null;
  action: string;
  payload: Record<string, any>;
  previous_hash: string;
  current_hash: string;
  timestamp: string;
}

export interface AuditVerificationResult {
  is_valid: boolean;
  total_records: number;
  tampered_sequence_id?: number | null;
  verification_message: string;
  has_historical_break?: boolean;
  historical_break_notes?: string | null;
}

// -----------------------------------------------------------------------------
// API Service Methods
// -----------------------------------------------------------------------------

export const authApi = {
  async login(email: string, password: string = 'DemoSecure2026!') {
    const res = await apiClient.post('/auth/login', { email, password });
    const token = res.data.access_token;
    localStorage.setItem('brandshield_token', token);
    return res.data;
  },

  async signup(data: { email: string; password: string; full_name: string; role?: 'CREATOR' | 'REVIEWER' | 'ADMINISTRATOR' }) {
    const res = await apiClient.post('/auth/signup', data);
    const token = res.data.access_token;
    localStorage.setItem('brandshield_token', token);
    return res.data;
  },

  async getMe(): Promise<CurrentUser> {
    const res = await apiClient.get('/auth/me');
    return res.data;
  },

  logout() {
    localStorage.removeItem('brandshield_token');
  },
};

export const dashboardApi = {
  async getSummary(): Promise<DashboardSummary> {
    const res = await apiClient.get('/submissions/dashboard/summary');
    return res.data;
  },

  async getGovernanceReport(brandProfileId?: string): Promise<GovernanceReport> {
    const q = brandProfileId ? `?brand_profile_id=${brandProfileId}` : '';
    const res = await apiClient.get(`/governance/reports${q}`);
    return res.data;
  },
};

export const submissionsApi = {
  async list(workflowState?: string): Promise<SubmissionItem[]> {
    const q = workflowState && workflowState !== 'ALL' ? `?workflow_state=${workflowState}` : '';
    const res = await apiClient.get(`/submissions/${q}`);
    return res.data;
  },

  async get(id: string): Promise<SubmissionItem> {
    const res = await apiClient.get(`/submissions/${id}`);
    return res.data;
  },

  async submitText(title: string, brandProfileId: string, content: string): Promise<SubmissionItem> {
    const res = await apiClient.post('/submissions/text', {
      title,
      brand_profile_id: brandProfileId,
      content,
      document_type: 'TEXT',
    });
    return res.data;
  },

  async uploadFile(title: string, brandProfileId: string, file: File): Promise<SubmissionItem> {
    const formData = new FormData();
    formData.append('title', title);
    formData.append('brand_profile_id', brandProfileId);
    formData.append('file', file);
    const res = await apiClient.post('/submissions/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  async listRevisions(submissionId: string): Promise<DocumentRevision[]> {
    const res = await apiClient.get(`/submissions/${submissionId}/revisions`);
    return res.data;
  },

  async getRevisionDiff(submissionId: string, baseRevision: number = 1, targetRevision: number = 2): Promise<RevisionDiff> {
    const res = await apiClient.get(`/workflow/${submissionId}/revisions/diff?base_revision=${baseRevision}&target_revision=${targetRevision}`);
    return res.data;
  },
};

export const analysisApi = {
  async analyzeLive(contentText: string, brandProfileId: string, requestedProvider: string = 'Azure OpenAI') {
    const res = await apiClient.post('/analysis/live', {
      content_text: contentText,
      brand_profile_id: brandProfileId,
      requested_provider: requestedProvider,
    });
    return res.data;
  },

  async runOnSubmission(submissionId: string) {
    const res = await apiClient.post(`/analysis/submissions/${submissionId}/run`);
    return res.data;
  },

  async getFindingsForRevision(revisionId: string): Promise<FindingItem[]> {
    const res = await apiClient.get(`/analysis/revisions/${revisionId}/findings`);
    return res.data;
  },
};

export const workflowApi = {
  async resolveFinding(
    submissionId: string,
    findingId: string,
    action: 'ACCEPT' | 'ACCEPTED' | 'ACCEPT_SUGGESTION' | 'CUSTOM_EDIT' | 'REJECT_WITH_RATIONALE' | 'REJECTED' | 'EDITED',
    customReplacement?: string,
    rationale?: string
  ) {
    const res = await apiClient.post(`/workflow/${submissionId}/findings/${findingId}/resolve`, {
      action: action === 'ACCEPT_SUGGESTION' ? 'ACCEPTED' : action === 'CUSTOM_EDIT' ? 'EDITED' : action === 'REJECT_WITH_RATIONALE' ? 'REJECTED' : action,
      edited_text: customReplacement,
      comment: rationale,
      custom_replacement: customReplacement,
      rationale,
    });
    return res.data;
  },

  async submitForReview(submissionId: string): Promise<SubmissionItem> {
    const res = await apiClient.post(`/workflow/${submissionId}/submit-for-review`);
    return res.data;
  },

  async reviewDecision(
    submissionId: string,
    decision: 'APPROVED' | 'CHANGES_REQUESTED',
    comments: string,
    findingVerifications?: { finding_id: string; verified: boolean; comment?: string }[]
  ) {
    const res = await apiClient.post(`/workflow/${submissionId}/review`, {
      decision,
      comments,
      finding_verifications: findingVerifications,
    });
    return res.data;
  },

  async getReviews(submissionId: string) {
    const res = await apiClient.get(`/workflow/${submissionId}/reviews`);
    return res.data;
  },

  async assignReviewer(submissionId: string, reviewerId?: string) {
    const res = await apiClient.post(`/workflow/${submissionId}/assign-reviewer${reviewerId ? `?target_reviewer_id=${reviewerId}` : ''}`);
    return res.data;
  },
};

export const brandsApi = {
  async getActiveProfile(): Promise<BrandProfileItem | null> {
    try {
      const res = await apiClient.get<BrandProfileItem>('/brands/active-profile');
      return res.data;
    } catch {
      return null;
    }
  },

  async listProfiles(): Promise<BrandProfileItem[]> {
    // Try admin profiles first; fall back to specific seeded profile
    try {
      const res = await apiClient.get('/brands/profiles');
      return res.data;
    } catch {
      return [];
    }
  },

  async getGuidelines(profileId: string): Promise<BrandGuidelineItem[]> {
    const res = await apiClient.get(`/brands/profiles/${profileId}/guidelines`);
    return res.data;
  },

  async listFacts(): Promise<ApprovedFactItem[]> {
    const res = await apiClient.get('/brands/facts');
    return res.data;
  },

  async createGuideline(profileId: string, guideline: {
    clause_identifier: string;
    clause_text: string;
    category: string;
    severity: string;
    embedding: number[];
  }): Promise<BrandGuidelineItem> {
    const res = await apiClient.post(`/brands/profiles/${profileId}/guidelines`, guideline);
    return res.data;
  },

  async createFact(fact: {
    fact_statement: string;
    original_source_url: string;
    evidence_excerpt: string;
    verification_date: string;
    expiry_date: string;
    responsible_owner_id: string;
    brand_profile_id?: string;
    embedding: number[];
  }): Promise<ApprovedFactItem> {
    const res = await apiClient.post('/brands/facts', fact);
    return res.data;
  },
};

export const auditApi = {
  async getLogs(limit: number = 50): Promise<AuditLogItem[]> {
    const res = await apiClient.get(`/audit/logs?limit=${limit}`);
    return res.data;
  },

  async verifyChain(): Promise<AuditVerificationResult> {
    const res = await apiClient.post('/governance/audit-verify');
    return res.data;
  },
};

export interface ReviewRules {
  confidence_threshold: number;
  random_double_check_percentage: number;
  fact_review_period_days: number;
  require_evidence_before_approval: boolean;
}

export interface SystemStatusInfo {
  backend_connection: string;
  audit_chain_status: string;
  chain_valid: boolean;
  has_historical_break?: boolean;
  total_records?: number;
}

export const settingsApi = {
  async getReviewRules(): Promise<ReviewRules> {
    const res = await apiClient.get('/settings/review-rules');
    return res.data;
  },
  async updateReviewRules(rules: ReviewRules): Promise<ReviewRules> {
    const res = await apiClient.put('/settings/review-rules', rules);
    return res.data;
  },
  async getSystemStatus(): Promise<SystemStatusInfo> {
    const res = await apiClient.get('/settings/system-status');
    return res.data;
  },
};
