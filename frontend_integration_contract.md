# BrandShield AI - Frontend Integration Contract & TypeScript API Specification

> **Version:** 1.0.0  
> **Base URL:** `http://localhost:8000/api/v1` (Dev) / `https://api.brandshield.ai/api/v1` (Prod)  
> **Target Frontend Stack:** React 18+ / Next.js, TypeScript 5+, Tailwind CSS, Axios / SWR / React Query, Recharts.  
> **Authentication:** Standard JWT Bearer in `Authorization: Bearer <token>` header, or `?token=<jwt>` query parameter for SSE `EventSource`.

---

## 1. Authentication & Tenant Routing

### TypeScript Interfaces

```typescript
export type UserRole = "ADMINISTRATOR" | "REVIEWER" | "CREATOR" | "AUDITOR";

export interface LoginPayload {
  email: string;
  password: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in_seconds: number;
}

export interface UserProfile {
  id: string; // UUID
  workspace_id: string; // UUID
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string; // ISO 8601
}
```

### Axios Client Setup

```typescript
// src/api/client.ts
import axios from "axios";

export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("brandshield_access_token");
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      error.config._retry = true;
      const refreshToken = localStorage.getItem("brandshield_refresh_token");
      if (refreshToken) {
        try {
          const { data } = await axios.post<AuthTokens>(
            `${apiClient.defaults.baseURL}/auth/refresh`,
            { refresh_token: refreshToken }
          );
          localStorage.setItem("brandshield_access_token", data.access_token);
          error.config.headers.Authorization = `Bearer ${data.access_token}`;
          return apiClient(error.config);
        } catch {
          localStorage.removeItem("brandshield_access_token");
          localStorage.removeItem("brandshield_refresh_token");
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  }
);
```

---

## 2. Real-Time SSE Pipeline Streaming (`GET /api/v1/submissions/{id}/analyze/stream`)

Streams real-time pipeline progress across all four intelligence stages with millisecond latencies to the React dashboard.

### TypeScript SSE Stage Contracts

```typescript
export type PipelineStage =
  | "STAGE_1_DETERMINISTIC_COMPLETE"
  | "STAGE_2_TEMPORAL_FACT_RAG_COMPLETE"
  | "STAGE_3_PRIVACY_GATE_VERIFIED"
  | "STAGE_4_TRIAGE_COMPLETE"
  | "PIPELINE_COMPLETE"
  | "PIPELINE_ERROR";

export interface SSEStage1Data {
  stage: "STAGE_1_DETERMINISTIC_COMPLETE";
  latency_ms: number;
  findings_count: number;
  summary: string;
}

export interface SSEStage2Data {
  stage: "STAGE_2_TEMPORAL_FACT_RAG_COMPLETE";
  latency_ms: number;
  temporal_claims_count: number;
  stale_facts: number;
  missing_evidence: number;
  summary: string;
}

export interface SSEStage3Data {
  stage: "STAGE_3_PRIVACY_GATE_VERIFIED";
  latency_ms: number;
  provider: string;
  tone_hits_count: number;
  pii_redacted: boolean;
  summary: string;
}

export interface SSEStage4Data {
  stage: "STAGE_4_TRIAGE_COMPLETE";
  latency_ms: number;
  total_findings: number;
  high_confidence: number;
  routed_to_human: number;
  stale_facts: number;
  missing_evidence: number;
  automation_bias_audits: number;
}

export interface SSEPipelineCompleteData {
  stage: "PIPELINE_COMPLETE";
  status: "SUCCESS";
  revision_id: string;
  total_findings: number;
  duration_ms: number;
  findings: FindingSummary[];
}

export interface FindingSummary {
  id: string;
  issue_category: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  confidence_score: number;
  triage_status: "FLAGGED_HIGH_CONFIDENCE" | "ROUTED_TO_HUMAN_LOW_CONFIDENCE" | "AUTO_CLEARED" | "STALE_FACT_REVERIFY" | "NEEDS_VERIFICATION_MISSING_EVIDENCE";
  start_offset: number;
  end_offset: number;
  explanation_reason: string;
  suggested_correction: string | null;
}
```

### React Hook: `useDocumentAnalysisStream`

```typescript
// src/hooks/useDocumentAnalysisStream.ts
import { useState, useEffect, useRef, useCallback } from "react";

export interface StreamState {
  isStreaming: boolean;
  activeStage: PipelineStage | null;
  stage1: SSEStage1Data | null;
  stage2: SSEStage2Data | null;
  stage3: SSEStage3Data | null;
  stage4: SSEStage4Data | null;
  complete: SSEPipelineCompleteData | null;
  error: string | null;
}

export function useDocumentAnalysisStream(submissionId: string | null) {
  const [state, setState] = useState<StreamState>({
    isStreaming: false,
    activeStage: null,
    stage1: null,
    stage2: null,
    stage3: null,
    stage4: null,
    complete: null,
    error: null,
  });

  const eventSourceRef = useRef<EventSource | null>(null);

  const startStream = useCallback(() => {
    if (!submissionId) return;

    const token = localStorage.getItem("brandshield_access_token");
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
    const url = `${baseUrl}/submissions/${submissionId}/analyze/stream?token=${encodeURIComponent(token || "")}`;

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setState((prev) => ({
      ...prev,
      isStreaming: true,
      error: null,
      activeStage: null,
    }));

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.addEventListener("STAGE_1_DETERMINISTIC_COMPLETE", (event: MessageEvent) => {
      const data = JSON.parse(event.data) as SSEStage1Data;
      setState((prev) => ({
        ...prev,
        activeStage: "STAGE_1_DETERMINISTIC_COMPLETE",
        stage1: data,
      }));
    });

    es.addEventListener("STAGE_2_TEMPORAL_FACT_RAG_COMPLETE", (event: MessageEvent) => {
      const data = JSON.parse(event.data) as SSEStage2Data;
      setState((prev) => ({
        ...prev,
        activeStage: "STAGE_2_TEMPORAL_FACT_RAG_COMPLETE",
        stage2: data,
      }));
    });

    es.addEventListener("STAGE_3_PRIVACY_GATE_VERIFIED", (event: MessageEvent) => {
      const data = JSON.parse(event.data) as SSEStage3Data;
      setState((prev) => ({
        ...prev,
        activeStage: "STAGE_3_PRIVACY_GATE_VERIFIED",
        stage3: data,
      }));
    });

    es.addEventListener("STAGE_4_TRIAGE_COMPLETE", (event: MessageEvent) => {
      const data = JSON.parse(event.data) as SSEStage4Data;
      setState((prev) => ({
        ...prev,
        activeStage: "STAGE_4_TRIAGE_COMPLETE",
        stage4: data,
      }));
    });

    es.addEventListener("PIPELINE_COMPLETE", (event: MessageEvent) => {
      const data = JSON.parse(event.data) as SSEPipelineCompleteData;
      setState((prev) => ({
        ...prev,
        isStreaming: false,
        activeStage: "PIPELINE_COMPLETE",
        complete: data,
      }));
      es.close();
    });

    es.addEventListener("PIPELINE_ERROR", (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      setState((prev) => ({
        ...prev,
        isStreaming: false,
        error: data.error || "Analysis pipeline execution encountered an error",
      }));
      es.close();
    });

    es.onerror = () => {
      setState((prev) => ({
        ...prev,
        isStreaming: false,
        error: "Connection lost with intelligence stream server.",
      }));
      es.close();
    };
  }, [submissionId]);

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return {
    ...state,
    startStream,
  };
}
```

---

## 3. Governance Reports with Pre-formatted Recharts Models (`GET /api/v1/governance/reports`)

Pre-formatted data contracts directly bindable to React `Recharts` charts without client-side data crunching.

### TypeScript Governance Interfaces

```typescript
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
  date: string; // YYYY-MM-DD
  approved: number;
  changes_requested: number;
  total_reviews: number;
}

export interface RechartsTriagePie {
  name: string;
  value: number;
  fill: string; // Hex color code (e.g. "#10B981")
  key?: string; // "HIGH" | "MEDIUM" | "LOW"
  percentage: number; // 0.0 - 100.0
}

export interface GovernanceReportResponse {
  workspace_id: string;
  brand_profile_id: string | null;
  total_findings: number;
  category_counts: Record<string, number>;
  severity_counts: Record<string, number>;
  triage_status_counts: Record<string, number>;
  detector_source_counts: Record<string, number>;
  creator_action_counts: Record<string, number>;
  category_severity_cube: Array<{
    issue_category: string | null;
    severity: string | null;
    count: number;
  }>;
  // Pre-formatted Recharts datasets
  recharts_category_bar: RechartsCategoryBar[];
  recharts_review_trends_line: RechartsReviewTrendLine[];
  recharts_triage_pie: RechartsTriagePie[];
  generated_at: string;
}
```

### Drop-in Recharts Component Snippets

```tsx
// src/components/governance/GovernanceCharts.tsx
import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { GovernanceReportResponse } from "@/types";

export const RecurringIssuesBarChart: React.FC<{ data: GovernanceReportResponse["recharts_category_bar"] }> = ({ data }) => (
  <div className="w-full h-80 p-4 bg-slate-900 border border-slate-800 rounded-xl">
    <h3 className="text-white text-base font-semibold mb-4">Recurring Compliance Issues</h3>
    <ResponsiveContainer width="100%" height="90%">
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis dataKey="name" stroke="#94A3B8" tick={{ fontSize: 12 }} />
        <YAxis stroke="#94A3B8" />
        <Tooltip contentStyle={{ backgroundColor: "#0F172A", borderColor: "#334155", color: "#F8FAFC" }} />
        <Legend />
        <Bar dataKey="CRITICAL" stackId="a" fill="#EF4444" name="Critical" />
        <Bar dataKey="HIGH" stackId="a" fill="#F97316" name="High" />
        <Bar dataKey="MEDIUM" stackId="a" fill="#F59E0B" name="Medium" />
        <Bar dataKey="LOW" stackId="a" fill="#3B82F6" name="Low" />
      </BarChart>
    </ResponsiveContainer>
  </div>
);

export const ReviewTrendsLineChart: React.FC<{ data: GovernanceReportResponse["recharts_review_trends_line"] }> = ({ data }) => (
  <div className="w-full h-80 p-4 bg-slate-900 border border-slate-800 rounded-xl">
    <h3 className="text-white text-base font-semibold mb-4">Review Decisions Over Time</h3>
    <ResponsiveContainer width="100%" height="90%">
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis dataKey="date" stroke="#94A3B8" tick={{ fontSize: 12 }} />
        <YAxis stroke="#94A3B8" />
        <Tooltip contentStyle={{ backgroundColor: "#0F172A", borderColor: "#334155", color: "#F8FAFC" }} />
        <Legend />
        <Line type="monotone" dataKey="approved" stroke="#10B981" strokeWidth={2} name="Approved" />
        <Line type="monotone" dataKey="changes_requested" stroke="#F43F5E" strokeWidth={2} name="Changes Requested" />
        <Line type="monotone" dataKey="total_reviews" stroke="#8B5CF6" strokeWidth={1} strokeDasharray="5 5" name="Total Activity" />
      </LineChart>
    </ResponsiveContainer>
  </div>
);

export const TriageConfidencePieChart: React.FC<{ data: GovernanceReportResponse["recharts_triage_pie"] }> = ({ data }) => (
  <div className="w-full h-80 p-4 bg-slate-900 border border-slate-800 rounded-xl">
    <h3 className="text-white text-base font-semibold mb-4">Triage Confidence Distribution</h3>
    <ResponsiveContainer width="100%" height="90%">
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={90}
          paddingAngle={5}
          dataKey="value"
          nameKey="name"
          label={({ name, percentage }) => `${name}: ${percentage}%`}
        >
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.fill} />
          ))}
        </Pie>
        <Tooltip contentStyle={{ backgroundColor: "#0F172A", borderColor: "#334155", color: "#F8FAFC" }} />
      </PieChart>
    </ResponsiveContainer>
  </div>
);
```

---

## 4. Submissions, Documents & AST Tokenization

### TypeScript Endpoints & DTOs

```typescript
export interface ASTSpan {
  id: string;
  start_char: number;
  end_char: number;
  text_snippet: string;
  block_type: "PARAGRAPH" | "HEADING" | "LIST_ITEM" | "CAPTION" | "TABLE_CELL";
  page_number?: number;
  style_flags?: {
    is_bold?: boolean;
    is_italic?: boolean;
    all_caps?: boolean;
    font_size?: number;
  };
}

export interface DocumentRevision {
  id: string; // UUID
  submission_id: string;
  revision_number: number;
  parent_revision_id: string | null;
  content_text: string;
  ast_span_map: ASTSpan[];
  sha256_content_hash: string;
  created_at: string;
}

export interface Submission {
  id: string; // UUID
  workspace_id: string;
  brand_profile_id: string;
  creator_id: string;
  assigned_reviewer_id: string | null;
  title: string;
  document_type: "PDF" | "DOCX" | "TEXT" | "MARKDOWN";
  workflow_state: "SUBMITTED" | "TRIAGED" | "IN_REVIEW" | "APPROVED" | "CHANGES_REQUESTED";
  current_revision_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TextSubmissionPayload {
  brand_profile_id: string;
  title: string;
  content: string;
  document_type?: "TEXT" | "MARKDOWN";
}

export interface RevisionDiffResponse {
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
```

### Axios Hooks for Document Ingestion

```typescript
// src/api/submissions.ts
import { apiClient } from "./client";
import { Submission, TextSubmissionPayload, RevisionDiffResponse } from "@/types";

export async function submitTextDocument(payload: TextSubmissionPayload): Promise<Submission> {
  const { data } = await apiClient.post<Submission>("/submissions/text", payload);
  return data;
}

export async function submitFileDocument(
  file: File,
  brandProfileId: string,
  title: string
): Promise<Submission> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("brand_profile_id", brandProfileId);
  formData.append("title", title);

  const { data } = await apiClient.post<Submission>("/submissions/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getRevisionDiff(
  submissionId: string,
  baseRevision: number,
  targetRevision: number
): Promise<RevisionDiffResponse> {
  const { data } = await apiClient.get<RevisionDiffResponse>(
    `/submissions/${submissionId}/revisions/diff`,
    {
      params: { base_revision: baseRevision, target_revision: targetRevision },
    }
  );
  return data;
}
```

---

## 5. Reviewer Decisions & Workflow Endpoints

```typescript
export interface ReviewDecisionPayload {
  decision: "APPROVED" | "CHANGES_REQUESTED";
  comments: string;
  stipulations?: Record<string, unknown>;
}

export interface ReviewDecisionResponse {
  id: string;
  submission_id: string;
  revision_id: string;
  reviewer_id: string;
  decision: "APPROVED" | "CHANGES_REQUESTED";
  comments: string;
  stipulations: Record<string, unknown> | null;
  decided_at: string;
}

export async function submitReviewDecision(
  submissionId: string,
  payload: ReviewDecisionPayload
): Promise<ReviewDecisionResponse> {
  const { data } = await apiClient.post<ReviewDecisionResponse>(
    `/submissions/${submissionId}/decisions`,
    payload
  );
  return data;
}
```

---

## 6. Zero-Trust Error Handling (RFC 7807 Problem Details)

All backend error responses adhere strictly to **RFC 7807**:

```typescript
export interface ProblemDetails {
  type: string; // "urn:brandshield:error:forbidden"
  title: string;
  status: number; // 403, 404, 422, etc.
  detail: string;
  instance: string;
  correlation_id: string; // Telemetry correlation UUID
  errors?: Array<{ field: string; message: string }>;
}
```
