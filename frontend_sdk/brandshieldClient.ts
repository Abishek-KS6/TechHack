/**
 * BrandShield AI - Zero-Dependency Enterprise TypeScript SDK
 * Engineered for React 18+, Next.js 14+, Vite, and vanilla TypeScript frontends.
 * Features strict types matching Pydantic v2 backend schemas, typed fetch wrappers,
 * Server-Sent Events (SSE) analysis streaming, and Recharts-ready analytics hooks.
 */

export type UserRole = "CREATOR" | "REVIEWER" | "ADMINISTRATOR";
export type WorkflowState =
  | "SUBMITTED"
  | "ANALYZING"
  | "TRIAGED"
  | "IN_CREATOR_REVISION"
  | "IN_HUMAN_REVIEW"
  | "CHANGES_REQUESTED"
  | "APPROVED";

export type FindingCategory =
  | "TONE"
  | "TERMINOLOGY"
  | "MESSAGING"
  | "ACCESSIBILITY"
  | "UNSUBSTANTIATED_CLAIM"
  | "STALE_FACT"
  | "REGULATORY_VIOLATION";

export type SeverityLevel = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type TriageStatus =
  | "FLAGGED_HIGH_CONFIDENCE"
  | "ROUTED_TO_HUMAN_LOW_CONFIDENCE"
  | "STALE_FACT_REVERIFY"
  | "NEEDS_VERIFICATION_MISSING_EVIDENCE"
  | "CLEARED_COMPLIANT";

export type ReviewSignOff = "APPROVED" | "CHANGES_REQUESTED";

// =============================================================================
// Domain Contracts & Schemas
// =============================================================================

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds?: number;
  role: UserRole;
  user_id: string;
  workspace_id: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  workspace_id: string;
  is_active: boolean;
  created_at: string;
}

export interface BrandProfile {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  tone_parameters: {
    target_formality?: number;
    max_grade_level?: number;
    max_passive_voice_ratio?: number;
    forbidden_sentiments?: string[];
  };
  banned_terminology_map: Record<
    string,
    { reason: string; severity: SeverityLevel; suggested_replacements?: string[] }
  >;
  preferred_terminology_map: Record<
    string,
    { approved_term: string; reason: string; severity: SeverityLevel }
  >;
  messaging_rules: {
    required_disclaimers?: string[];
    regulatory_framework?: string;
  };
  privacy_gate_config: {
    allow_external_llm: boolean;
    contract_verified_at?: string;
    approved_providers?: string[];
    retention_days?: number;
  };
  is_active: boolean;
  created_at: string;
}

export interface ASTSpanNode {
  id: string;
  node_type: string;
  text: string;
  start_char: number;
  end_char: number;
  page_number?: number;
  bbox?: [number, number, number, number];
}

export interface DocumentRevision {
  id: string;
  submission_id: string;
  revision_number: number;
  parent_revision_id: string | null;
  content_text: string;
  ast_span_map: ASTSpanNode[];
  created_by_id: string;
  sha256_content_hash: string;
  diff_summary?: Record<string, unknown> | null;
  created_at: string;
}

export interface Finding {
  id: string;
  revision_id: string;
  issue_category: FindingCategory;
  severity: SeverityLevel;
  confidence_score: number;
  triage_status: TriageStatus;
  start_offset: number;
  end_offset: number;
  highlighted_text?: string;
  explanation_reason: string;
  suggested_correction?: string | null;
  detector_source: string;
  linked_guideline_id?: string | null;
  linked_fact_id?: string | null;
  is_automation_bias_audit: boolean;
  creator_action?: string | null;
  created_at: string;
}

export interface Submission {
  id: string;
  workspace_id: string;
  creator_id: string;
  assigned_reviewer_id?: string | null;
  brand_profile_id: string;
  title: string;
  document_type: string;
  workflow_state: WorkflowState;
  current_revision_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewDecision {
  id: string;
  submission_id: string;
  revision_id: string;
  reviewer_id: string;
  decision: ReviewSignOff;
  comments: string;
  stipulations?: Record<string, unknown> | null;
  created_at: string;
}

// Recharts Pre-Formatted Governance Data
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
  key?: string;
  percentage: number;
}

export interface GovernanceReportResponse {
  workspace_id: string;
  brand_profile_id?: string | null;
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

export interface TraceabilityMetricsResponse {
  workspace_id: string;
  brand_profile_id?: string | null;
  total_findings: number;
  grounded_findings_count: number;
  ungrounded_findings_count: number;
  traceability_percentage: number;
  guideline_linked_count: number;
  fact_linked_count: number;
  is_zero_ungrounded_verified: boolean;
  audit_timestamp: string;
}

export interface AuditChainVerificationResult {
  is_valid: boolean;
  total_records: number;
  tampered_sequence_id?: number | null;
  verification_message: string;
  chain_valid?: boolean;
}

export interface EvaluationBenchmarkResponse {
  total_samples: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  precision: number;
  recall: number;
  f1_score: number;
  p95_latency_ms: number;
  avg_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
  evaluated_at: string;
}

// =============================================================================
// Typed BrandShield AI Client
// =============================================================================

export class BrandShieldClient {
  private baseUrl: string;
  private token: string | null;

  constructor(baseUrl: string = "http://localhost:8000", token?: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.token = token || null;
  }

  public setToken(token: string): void {
    this.token = token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (this.token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(url, { ...options, headers });
    if (!response.ok) {
      let problemDetail: any = null;
      try {
        problemDetail = await response.json();
      } catch {
        // non-json response
      }
      throw new Error(
        problemDetail?.detail ||
          problemDetail?.title ||
          `API Request failed with status ${response.status}: ${response.statusText}`
      );
    }

    return response.json() as Promise<T>;
  }

  // ---------------------------------------------------------------------------
  // 1. Authentication
  // ---------------------------------------------------------------------------
  public async login(email: string, password: string): Promise<TokenResponse> {
    const formData = new URLSearchParams();
    formData.append("username", email);
    formData.append("password", password);

    const res = await this.request<TokenResponse>("/api/v1/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData.toString(),
    });
    this.setToken(res.access_token);
    return res;
  }

  public async getCurrentUser(): Promise<User> {
    return this.request<User>("/api/v1/auth/me");
  }

  // ---------------------------------------------------------------------------
  // 2. Brand Setup
  // ---------------------------------------------------------------------------
  public async getBrandProfile(profileId: string): Promise<BrandProfile> {
    return this.request<BrandProfile>(`/api/v1/brands/${profileId}`);
  }

  // ---------------------------------------------------------------------------
  // 3. Submissions & Document Ingestion
  // ---------------------------------------------------------------------------
  public async submitText(
    title: string,
    brandProfileId: string,
    content: string
  ): Promise<Submission> {
    return this.request<Submission>("/api/v1/submissions/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        brand_profile_id: brandProfileId,
        content,
        document_type: "TEXT",
      }),
    });
  }

  public async uploadDocument(
    title: string,
    brandProfileId: string,
    file: Blob | File,
    filename: string
  ): Promise<Submission> {
    const formData = new FormData();
    formData.append("title", title);
    formData.append("brand_profile_id", brandProfileId);
    formData.append("file", file, filename);

    return this.request<Submission>("/api/v1/submissions/upload", {
      method: "POST",
      body: formData,
    });
  }

  public async getSubmission(submissionId: string): Promise<Submission> {
    return this.request<Submission>(`/api/v1/submissions/${submissionId}`);
  }

  public async listRevisions(submissionId: string): Promise<DocumentRevision[]> {
    return this.request<DocumentRevision[]>(
      `/api/v1/submissions/${submissionId}/revisions`
    );
  }

  public async getRevisionDiff(
    submissionId: string,
    fromRevision: number = 1,
    toRevision?: number
  ): Promise<any> {
    const q = new URLSearchParams({ from_revision: fromRevision.toString() });
    if (toRevision) q.append("to_revision", toRevision.toString());
    return this.request(`/api/v1/workflow/${submissionId}/revisions/diff?${q.toString()}`);
  }

  // ---------------------------------------------------------------------------
  // 4. Real-Time SSE Analysis Stream
  // ---------------------------------------------------------------------------
  public streamAnalysis(
    submissionId: string,
    callbacks: {
      onStage?: (stage: string, latencyMs: number) => void;
      onFinding?: (finding: Finding) => void;
      onComplete?: (totalFindings: number, durationMs: number) => void;
      onError?: (error: Error) => void;
    }
  ): () => void {
    const url = `${this.baseUrl}/api/v1/submissions/${submissionId}/analyze/stream?token=${encodeURIComponent(
      this.token || ""
    )}`;

    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.stage && callbacks.onStage) {
          callbacks.onStage(payload.stage, payload.latency_ms || 0);
        }
        if (payload.findings && Array.isArray(payload.findings) && callbacks.onFinding) {
          payload.findings.forEach((f: Finding) => callbacks.onFinding?.(f));
        }
        if (payload.stage === "PIPELINE_COMPLETE") {
          callbacks.onComplete?.(payload.total_findings || 0, payload.duration_ms || 0);
          eventSource.close();
        }
      } catch (err: any) {
        callbacks.onError?.(err);
      }
    };

    eventSource.onerror = (err) => {
      callbacks.onError?.(new Error("SSE Stream error occurred"));
      eventSource.close();
    };

    return () => eventSource.close();
  }

  // ---------------------------------------------------------------------------
  // 5. Creator Revision Resolution & Reviewer Sign-off
  // ---------------------------------------------------------------------------
  public async resolveFinding(
    findingId: string,
    action: "ACCEPT_SUGGESTION" | "CUSTOM_EDIT" | "REJECT_WITH_RATIONALE",
    customReplacement?: string,
    rationale?: string
  ): Promise<any> {
    return this.request(`/api/v1/workflow/findings/${findingId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action,
        custom_replacement: customReplacement,
        rationale,
      }),
    });
  }

  public async submitForReview(submissionId: string): Promise<Submission> {
    return this.request<Submission>(`/api/v1/workflow/${submissionId}/submit-for-review`, {
      method: "POST",
    });
  }

  public async executeReviewDecision(
    submissionId: string,
    decision: ReviewSignOff,
    comments: string,
    stipulations?: Record<string, unknown>
  ): Promise<ReviewDecision> {
    return this.request<ReviewDecision>(`/api/v1/workflow/${submissionId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        comments,
        stipulations,
      }),
    });
  }

  // ---------------------------------------------------------------------------
  // 6. Governance & Recharts Analytics
  // ---------------------------------------------------------------------------
  public async getGovernanceReports(
    brandProfileId?: string
  ): Promise<GovernanceReportResponse> {
    const q = brandProfileId ? `?brand_profile_id=${brandProfileId}` : "";
    return this.request<GovernanceReportResponse>(`/api/v1/governance/reports${q}`);
  }

  public async getTraceabilityMetrics(
    brandProfileId?: string
  ): Promise<TraceabilityMetricsResponse> {
    const q = brandProfileId ? `?brand_profile_id=${brandProfileId}` : "";
    return this.request<TraceabilityMetricsResponse>(
      `/api/v1/governance/traceability-metrics${q}`
    );
  }

  public async verifyAuditChain(): Promise<AuditChainVerificationResult> {
    return this.request<AuditChainVerificationResult>(
      "/api/v1/governance/audit-verify",
      { method: "POST" }
    );
  }

  public async runEvaluationBenchmark(
    brandProfileId?: string
  ): Promise<EvaluationBenchmarkResponse> {
    const q = brandProfileId ? `?brand_profile_id=${brandProfileId}` : "";
    return this.request<EvaluationBenchmarkResponse>(
      `/api/v1/governance/evaluate-testset${q}`,
      { method: "POST" }
    );
  }
}
