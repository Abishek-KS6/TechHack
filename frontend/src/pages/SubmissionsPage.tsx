import React, { useState, useEffect } from 'react';
import {
  submissionsApi,
  analysisApi,
  workflowApi,
  type SubmissionItem,
  type DocumentRevision,
  type FindingItem,
  type RevisionDiff
} from '../api/client';
import { useAuth } from '../context/AuthContext';
import ThreeDRevisionDag from '../components/ThreeDRevisionDag';
import TiltCard from '../components/TiltCard';

const STATUS_BADGE: Record<string, string> = {
  APPROVED: 'badge-success',
  IN_HUMAN_REVIEW: 'badge-warning',
  TRIAGED: 'badge-info',
  SUBMITTED: 'badge-info',
  IN_CREATOR_REVISION: 'badge-warning',
  CHANGES_REQUESTED: 'badge-danger',
};

export default function SubmissionsPage() {
  const { role, user, activeBrandProfileId } = useAuth();
  const [submissions, setSubmissions] = useState<SubmissionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState<string>('');
  const [filter, setFilter] = useState<string>('ALL');

  // New submission modal state
  const [showModal, setShowModal] = useState<boolean>(false);
  const [subType, setSubType] = useState<'text' | 'file'>('text');
  const [newTitle, setNewTitle] = useState<string>('');
  const [newContent, setNewContent] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Detail drawer / modal state
  const [selectedSub, setSelectedSub] = useState<SubmissionItem | null>(null);
  const [revisions, setRevisions] = useState<DocumentRevision[]>([]);
  const [reviews, setReviews] = useState<any[]>([]);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [diff, setDiff] = useState<RevisionDiff | null>(null);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [reviewerComment, setReviewerComment] = useState<string>('');
  const [activeFindingEditId, setActiveFindingEditId] = useState<string | null>(null);
  const [customEditText, setCustomEditText] = useState<string>('');
  const [activeFindingRejectId, setActiveFindingRejectId] = useState<string | null>(null);
  const [rejectRationale, setRejectRationale] = useState<string>('');
  const [verifiedAudits, setVerifiedAudits] = useState<Record<string, boolean>>({});

  const fetchSubmissions = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await submissionsApi.list(filter);
      setSubmissions(data || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load submissions from database.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSubmissions();
  }, [filter, role]);

  const handleCreateSubmission = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) {
      setSubmitError('Document title is required.');
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      let created: SubmissionItem;
      if (subType === 'text') {
        if (!newContent.trim()) {
          setSubmitError('Document text content is required.');
          setSubmitting(false);
          return;
        }
        created = await submissionsApi.submitText(newTitle, activeBrandProfileId, newContent);
      } else {
        if (!selectedFile) {
          setSubmitError('Please select a PDF or DOCX file to upload.');
          setSubmitting(false);
          return;
        }
        created = await submissionsApi.uploadFile(newTitle, activeBrandProfileId, selectedFile);
      }

      setShowModal(false);
      setNewTitle('');
      setNewContent('');
      setSelectedFile(null);
      await fetchSubmissions();
      // Open the newly created submission
      openSubmissionDetails(created);
    } catch (err: any) {
      setSubmitError(err.message || 'Submission creation failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const openSubmissionDetails = async (sub: SubmissionItem) => {
    setSelectedSub(sub);
    setActionMessage(null);
    setActionLoading(true);
    try {
      const revs = await submissionsApi.listRevisions(sub.id);
      setRevisions(revs || []);

      if (sub.current_revision_id) {
        try {
          const fList = await analysisApi.getFindingsForRevision(sub.current_revision_id);
          setFindings(fList || []);
        } catch {
          setFindings([]);
        }
      } else {
        setFindings([]);
      }

      // If multiple revisions exist, fetch diff
      if (revs && revs.length > 1) {
        try {
          const diffData = await submissionsApi.getRevisionDiff(sub.id, 1, revs.length);
          setDiff(diffData);
        } catch {
          setDiff(null);
        }
      } else {
        setDiff(null);
      }

      // Fetch official review determinations & comments
      try {
        const revHistory = await workflowApi.getReviews(sub.id);
        setReviews(revHistory || []);
      } catch {
        setReviews([]);
      }
    } catch (err: any) {
      setActionMessage(`Error loading submission details: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRunAnalysis = async () => {
    if (!selectedSub) return;
    setActionLoading(true);
    setActionMessage(null);
    try {
      const result = await analysisApi.runOnSubmission(selectedSub.id);
      setActionMessage(`Analysis complete: ${result.total_findings} findings detected in ${result.processing_duration_ms?.toFixed(1) || '<1'}ms.`);
      // Reload submission and findings
      const updated = await submissionsApi.get(selectedSub.id);
      setSelectedSub(updated);
      if (updated.current_revision_id) {
        const fList = await analysisApi.getFindingsForRevision(updated.current_revision_id);
        setFindings(fList || []);
      }
      await fetchSubmissions();
    } catch (err: any) {
      setActionMessage(`Analysis failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResolveFinding = async (
    finding: FindingItem,
    action: 'ACCEPT_SUGGESTION' | 'CUSTOM_EDIT' | 'REJECT_WITH_RATIONALE',
    customReplacement?: string,
    rationale?: string
  ) => {
    if (!selectedSub) return;
    setActionLoading(true);
    setActionMessage(null);
    try {
      const res = await workflowApi.resolveFinding(
        selectedSub.id,
        finding.id,
        action,
        customReplacement || finding.suggested_correction || undefined,
        rationale || (action === 'CUSTOM_EDIT' ? 'Applied custom editor revision.' : action === 'REJECT_WITH_RATIONALE' ? 'Creator rationale provided.' : 'Applied automated correction suggestion.')
      );
      setActionMessage(`Finding resolved. Committed Revision #${res.new_revision_number}.`);
      setActiveFindingEditId(null);
      setActiveFindingRejectId(null);
      await openSubmissionDetails(await submissionsApi.get(selectedSub.id));
      await fetchSubmissions();
    } catch (err: any) {
      setActionMessage(`Resolution error: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSubmitForReview = async () => {
    if (!selectedSub) return;
    setActionLoading(true);
    setActionMessage(null);
    try {
      const updated = await workflowApi.submitForReview(selectedSub.id);
      setSelectedSub(updated);
      setActionMessage('Submission transitioned to IN_HUMAN_REVIEW queue.');
      await fetchSubmissions();
    } catch (err: any) {
      setActionMessage(`Workflow error: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const isCreatorOfSubmission = !!(user?.id && selectedSub && selectedSub.creator_id === user.id);
  const isAdminUnassigned = role === 'ADMINISTRATOR' && !!(selectedSub && selectedSub.assigned_reviewer_id !== user?.id);

  const handleAssignToMyself = async () => {
    if (!selectedSub) return;
    setActionLoading(true);
    setActionMessage(null);
    try {
      await workflowApi.assignReviewer(selectedSub.id);
      setActionMessage('Successfully assigned to yourself as reviewer.');
      const updated = await submissionsApi.get(selectedSub.id);
      setSelectedSub(updated);
      await fetchSubmissions();
    } catch (err: any) {
      setActionMessage(`Assignment error: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReviewDecision = async (decision: 'APPROVED' | 'CHANGES_REQUESTED') => {
    if (!selectedSub) return;
    setActionLoading(true);
    setActionMessage(null);

    // Automation-bias safeguard check: if approving, verify all flagged findings
    if (decision === 'APPROVED') {
      const unverifiedAudits = findings.filter((f) => f.is_automation_bias_audit && !verifiedAudits[f.id]);
      if (unverifiedAudits.length > 0) {
        setActionMessage(`Approval blocked: You must verify the supporting evidence for all ${unverifiedAudits.length} flagged automation-bias findings before approving.`);
        setActionLoading(false);
        return;
      }
    }

    try {
      const findingVerifications = findings
        .filter((f) => f.is_automation_bias_audit)
        .map((f) => ({
          finding_id: f.id,
          verified: !!verifiedAudits[f.id],
          comment: 'Verified evidence citation during human review.',
        }));

      await workflowApi.reviewDecision(
        selectedSub.id,
        decision,
        reviewerComment || (decision === 'APPROVED' ? 'Approved by compliance reviewer.' : 'Revisions requested.'),
        findingVerifications
      );
      const updated = await submissionsApi.get(selectedSub.id);
      setSelectedSub(updated);
      setReviewerComment('');
      setActionMessage(`Review recorded: ${decision}. State persisted.`);
      await openSubmissionDetails(updated);
      await fetchSubmissions();
    } catch (err: any) {
      setActionMessage(`Review error: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const filtered = submissions.filter((s) => {
    const matchSearch = s.title.toLowerCase().includes(search.toLowerCase());
    const matchFilter = filter === 'ALL' || s.workflow_state === filter;
    return matchSearch && matchFilter;
  });

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>Brand Submissions &amp; Lifecycle</h1>
          <p>Real-time submission ledger, immutable revision DAG, and reviewer governance workflow.</p>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => setShowModal(true)}>
          + New Submission
        </button>
      </div>

      {error && (
        <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', padding: 14, borderRadius: 8, marginBottom: 20, color: '#fca5a5' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Stats row */}
      <div className="grid-4" style={{ marginBottom: 24 }}>
        {[
          { label: 'Total Submissions', val: submissions.length, color: '#4f46e5', accent: 'rgba(99,102,241,0.18)' },
          { label: 'Approved', val: submissions.filter((s) => s.workflow_state === 'APPROVED').length, color: '#059669', accent: 'rgba(16,185,129,0.18)' },
          { label: 'In Review Queue', val: submissions.filter((s) => s.workflow_state === 'IN_HUMAN_REVIEW').length, color: '#d97706', accent: 'rgba(245,158,11,0.18)' },
          { label: 'Changes Requested', val: submissions.filter((s) => s.workflow_state === 'CHANGES_REQUESTED').length, color: '#dc2626', accent: 'rgba(239,68,68,0.18)' },
        ].map((s) => (
          <TiltCard key={s.label} maxTilt={8} glare={true} style={{ borderRadius: 'var(--radius-md)' }}>
            <div className="stat-card" style={{ '--card-accent': s.accent } as any}>
              <div className="stat-value" style={{ color: s.color, fontSize: 28, fontWeight: 800 }}>
                {loading ? '…' : s.val}
              </div>
              <div className="stat-label">{s.label}</div>
            </div>
          </TiltCard>
        ))}
      </div>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <div className="search-wrapper" style={{ flex: 1, minWidth: 220 }}>
          <input
            className="search-input"
            style={{ width: '100%' }}
            placeholder="Search submissions by title…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select className="form-select" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="ALL">All States</option>
          <option value="SUBMITTED">SUBMITTED</option>
          <option value="TRIAGED">TRIAGED</option>
          <option value="IN_CREATOR_REVISION">IN_CREATOR_REVISION</option>
          <option value="IN_HUMAN_REVIEW">IN_HUMAN_REVIEW</option>
          <option value="APPROVED">APPROVED</option>
          <option value="CHANGES_REQUESTED">CHANGES_REQUESTED</option>
        </select>
        <button className="btn btn-secondary btn-sm" onClick={fetchSubmissions}>
          Refresh
        </button>
      </div>

      {/* Submissions Table */}
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Title / ID</th>
              <th>Format</th>
              <th>Workflow State</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)' }}>
                  Loading database records…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)' }}>
                  No submissions match the current query. Click "+ New Submission" to ingest your first document.
                </td>
              </tr>
            ) : (
              filtered.map((s) => (
                <tr key={s.id}>
                  <td>
                    <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>{s.title}</div>
                    <div style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-muted)' }}>{s.id}</div>
                  </td>
                  <td>
                    <span className="tag">{s.document_type}</span>
                  </td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[s.workflow_state] || 'badge-info'}`}>
                      {s.workflow_state}
                    </span>
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {new Date(s.created_at).toLocaleDateString()} {new Date(s.created_at).toLocaleTimeString()}
                  </td>
                  <td>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => openSubmissionDetails(s)}
                    >
                      View &amp; Review →
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* New Submission Modal */}
      {showModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 20 }}>
          <div className="card" style={{ maxWidth: 640, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div className="card-title">Ingest New Content</div>
              <button
                onClick={() => setShowModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 20, cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>

            {submitError && (
              <div style={{ background: 'rgba(239,68,68,0.15)', border: '1px solid #ef4444', color: '#fca5a5', padding: 10, borderRadius: 6, marginBottom: 14, fontSize: 13 }}>
                {submitError}
              </div>
            )}

            <form onSubmit={handleCreateSubmission}>
              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
                  Document Title
                </label>
                <input
                  className="search-input"
                  style={{ width: '100%', paddingLeft: 12 }}
                  placeholder="e.g. Q3 Wealth Management Brochure"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  required
                />
              </div>

              <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
                <button
                  type="button"
                  className={`btn btn-sm ${subType === 'text' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setSubType('text')}
                >
                  Raw Copy / Markdown
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${subType === 'file' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setSubType('file')}
                >
                  Binary File (PDF / DOCX)
                </button>
              </div>

              {subType === 'text' ? (
                <div style={{ marginBottom: 16 }}>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
                    Content Text
                  </label>
                  <textarea
                    className="form-input"
                    style={{ minHeight: 180, width: '100%' }}
                    placeholder="Enter copy to establish Genesis Revision v1. (Try testing with banned terms like '100% risk-free' or 'foolproof' to trigger detections)..."
                    value={newContent}
                    onChange={(e) => setNewContent(e.target.value)}
                  />
                </div>
              ) : (
                <div style={{ marginBottom: 16 }}>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
                    Upload Supported Document (PDF or DOCX)
                  </label>
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      setIsDragging(true);
                    }}
                    onDragLeave={(e) => {
                      e.preventDefault();
                      setIsDragging(false);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      setIsDragging(false);
                      const file = e.dataTransfer.files?.[0];
                      if (file) {
                        if (!file.name.match(/\.(pdf|docx)$/i)) {
                          setSubmitError('Invalid file type. Only .pdf and .docx documents are supported.');
                          return;
                        }
                        if (file.size > 50 * 1024 * 1024) {
                          setSubmitError('File size exceeds the 50MB limit.');
                          return;
                        }
                        setSelectedFile(file);
                        setSubmitError(null);
                        if (!newTitle) {
                          setNewTitle(file.name.replace(/\.[^/.]+$/, ''));
                        }
                      }
                    }}
                    style={{
                      border: `2px dashed ${isDragging ? '#3b82f6' : selectedFile ? '#10b981' : 'var(--glass-border)'}`,
                      borderRadius: 12,
                      padding: '30px 20px',
                      textAlign: 'center',
                      background: isDragging ? 'rgba(59,130,246,0.1)' : selectedFile ? 'rgba(16,185,129,0.06)' : 'var(--glass-bg)',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onClick={() => document.getElementById('hidden-file-input')?.click()}
                  >
                    <input
                      id="hidden-file-input"
                      type="file"
                      accept=".pdf,.docx"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          if (file.size > 50 * 1024 * 1024) {
                            setSubmitError('File size exceeds 50MB limit.');
                            return;
                          }
                          setSelectedFile(file);
                          setSubmitError(null);
                          if (!newTitle) {
                            setNewTitle(file.name.replace(/\.[^/.]+$/, ''));
                          }
                        }
                      }}
                    />
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--brand-400)', marginBottom: 8 }}>
                      {selectedFile ? 'Document Selected' : isDragging ? 'Drop File' : 'Upload File'}
                    </div>
                    {selectedFile ? (
                      <div>
                        <div style={{ fontWeight: 600, color: '#34d399', fontSize: 14 }}>
                          {selectedFile.name}
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                          {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB · Click or drag another file to replace
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
                          Drag and drop your document here, or <span style={{ color: '#60a5fa', textDecoration: 'underline' }}>browse</span>
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                          Supports PDF (%PDF-1.x) and DOCX (PK ZIP OpenXML) up to 50MB
                        </div>
                      </div>
                    )}
                  </div>
                  {selectedFile && (
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedFile(null);
                        }}
                        style={{ background: 'none', border: 'none', color: '#f87171', fontSize: 11, cursor: 'pointer' }}
                      >
                        ✕ Remove file
                      </button>
                    </div>
                  )}
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
                    Content is parsed in a secure sandbox. AST coordinate maps &amp; SHA-256 integrity hashes are computed on ingestion.
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? 'Ingesting…' : 'Establish Genesis v1 & Ingest'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Submission Detail / Revision Inspector Modal */}
      {selectedSub && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 110, padding: 20 }}>
          <div className="card" style={{ maxWidth: 880, width: '100%', maxHeight: '92vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)' }}>{selectedSub.title}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'monospace' }}>ID: {selectedSub.id}</div>
              </div>
              <button
                onClick={() => setSelectedSub(null)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 20, cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>

            {actionMessage && (
              <div style={{ background: 'rgba(59,130,246,0.15)', border: '1px solid #3b82f6', color: '#93c5fd', padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 13 }}>
                {actionMessage}
              </div>
            )}

            {/* Workflow Control Bar */}
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', background: 'var(--glass-bg)', padding: 12, borderRadius: 8, marginBottom: 20, border: '1px solid var(--glass-border)' }}>
              <span className={`badge ${STATUS_BADGE[selectedSub.workflow_state] || 'badge-info'}`} style={{ alignSelf: 'center' }}>
                Status: {selectedSub.workflow_state}
              </span>

              {/* Action 1: Run 4-Stage Analysis */}
              <button
                className="btn btn-primary btn-sm"
                onClick={handleRunAnalysis}
                disabled={actionLoading}
              >
                Run 4-Stage Analysis
              </button>

              {/* Action 2: Creator Submit for Review */}
              {(selectedSub.workflow_state === 'IN_CREATOR_REVISION' || selectedSub.workflow_state === 'TRIAGED') && (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={handleSubmitForReview}
                  disabled={actionLoading}
                  style={{ background: '#7c3aed', color: '#fff' }}
                >
                  Submit for Human Review
                </button>
              )}
            </div>

            {/* Reviewer Sign-Off Box (If Reviewer or Admin and state is ready for review) */}
            {(role === 'REVIEWER' || role === 'ADMINISTRATOR') && (
              <div style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)', padding: 16, borderRadius: 8, marginBottom: 20 }}>
                <div style={{ fontWeight: 600, fontSize: 14, color: '#34d399', marginBottom: 8 }}>
                  Human Reviewer Governance Sign-Off (Role-Enforced)
                </div>

                {/* Separation of duties rule: Creator cannot approve their own submission */}
                {isCreatorOfSubmission && (
                  <div style={{ marginBottom: 12, padding: 10, background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444', borderRadius: 6, color: '#fca5a5', fontSize: 12 }}>
                    A creator cannot approve their own submission. (Separation of duties enforced)
                  </div>
                )}

                {/* Admin requirement: Admin cannot approve unless acting as assigned reviewer */}
                {!isCreatorOfSubmission && isAdminUnassigned && (
                  <div style={{ marginBottom: 12, padding: 10, background: 'rgba(59,130,246,0.1)', border: '1px solid #3b82f6', borderRadius: 6, color: '#93c5fd', fontSize: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                    <span>An administrator cannot approve unless acting as an assigned reviewer.</span>
                    <button
                      type="button"
                      className="btn btn-sm btn-secondary"
                      onClick={handleAssignToMyself}
                      disabled={actionLoading}
                      style={{ background: '#3b82f6', color: '#fff', border: 'none' }}
                    >
                      Assign to myself to review
                    </button>
                  </div>
                )}

                {/* Automation-bias verification mandatory checklist */}
                {findings.filter(f => f.is_automation_bias_audit).length > 0 && (
                  <div style={{ marginBottom: 12, padding: 10, background: 'rgba(245,158,11,0.08)', border: '1px solid #f59e0b', borderRadius: 6 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#fbbf24', marginBottom: 6 }}>
                      Automation-Bias Safeguard: Confirm Primary Evidence Citation Before Approval
                    </div>
                    {findings.filter(f => f.is_automation_bias_audit).map(f => (
                      <label key={f.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer', marginBottom: 6 }}>
                        <input
                          type="checkbox"
                          checked={!!verifiedAudits[f.id]}
                          onChange={(e) => setVerifiedAudits(prev => ({ ...prev, [f.id]: e.target.checked }))}
                          style={{ marginTop: 2 }}
                        />
                        <span>
                          <strong>{f.issue_category}:</strong> {f.explanation_reason}
                          {f.evidence_source && <span style={{ color: '#38bdf8' }}> — Source: {f.evidence_source}</span>}
                        </span>
                      </label>
                    ))}
                  </div>
                )}

                <input
                  className="search-input"
                  style={{ width: '100%', marginBottom: 10, paddingLeft: 10 }}
                  placeholder="Reviewer governance notes / stipulations…"
                  value={reviewerComment}
                  onChange={(e) => setReviewerComment(e.target.value)}
                />
                <div style={{ display: 'flex', gap: 10 }}>
                  <button
                    className="btn btn-sm"
                    style={{ background: '#10b981', color: '#fff', opacity: (isCreatorOfSubmission || isAdminUnassigned) ? 0.4 : 1 }}
                    onClick={() => handleReviewDecision('APPROVED')}
                    disabled={actionLoading || isCreatorOfSubmission || isAdminUnassigned}
                    title={
                      isCreatorOfSubmission
                        ? 'A creator cannot approve their own submission.'
                        : isAdminUnassigned
                        ? 'An administrator cannot approve unless acting as an assigned reviewer.'
                        : 'Approve Submission'
                    }
                  >
                    Approve Submission
                  </button>
                  <button
                    className="btn btn-sm"
                    style={{ background: '#ef4444', color: '#fff' }}
                    onClick={() => handleReviewDecision('CHANGES_REQUESTED')}
                    disabled={actionLoading || isCreatorOfSubmission}
                  >
                    Request Changes
                  </button>
                </div>
              </div>
            )}

            {/* 3D Isometric Revision History DAG */}
            <div style={{ marginBottom: 20 }}>
              <ThreeDRevisionDag
                revisions={revisions.map((rev) => ({
                  revision_number: rev.revision_number,
                  sha256_content_hash: rev.sha256_content_hash,
                  created_at: rev.created_at || '',
                  is_tip: rev.id === selectedSub.current_revision_id,
                  findings_count: findings.length,
                  approved: selectedSub.workflow_state === 'APPROVED',
                }))}
                activeRevision={revisions[revisions.length - 1]?.revision_number || 1}
              />

              {revisions.length > 0 && (
                <div style={{ background: 'var(--brand-950)', border: '1px solid var(--glass-border)', padding: 14, borderRadius: 8, maxHeight: 180, overflowY: 'auto', fontSize: 13, whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                  {revisions[revisions.length - 1].content_text}
                </div>
              )}

              {/* Review History Logs in Drawer */}
              {reviews.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 6 }}>
                    Recorded Reviewer Determinations &amp; Feedback:
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {reviews.map((rev) => (
                      <div key={rev.id} style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 6, border: '1px solid var(--glass-border)', fontSize: 12 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <span className={`badge ${rev.decision === 'APPROVED' ? 'badge-success' : 'badge-danger'}`} style={{ fontSize: 10 }}>
                            {rev.decision}
                          </span>
                          <span style={{ color: 'var(--text-muted)' }}>{new Date(rev.decided_at).toLocaleString()}</span>
                        </div>
                        <div style={{ color: 'var(--text-primary)' }}>{rev.comments}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Side-by-Side Unified Diff if multiple revisions exist */}
            {diff && (
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>
                  Immutable Diff (v{diff.base_revision_number} → v{diff.target_revision_number})
                </div>
                <div style={{ background: '#090d16', border: '1px solid #1e293b', padding: 12, borderRadius: 8, fontFamily: 'monospace', fontSize: 12, overflowX: 'auto', whiteSpace: 'pre-wrap' }}>
                  {diff.diff_unified || 'No text differences detected.'}
                </div>
              </div>
            )}

            {/* Findings List */}
            <div>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 10 }}>
                Triaged Findings on Current Revision ({findings.length})
              </div>
              {findings.length === 0 ? (
                <div style={{ color: '#34d399', fontSize: 13, background: 'rgba(16,185,129,0.08)', padding: 12, borderRadius: 8 }}>
                  Zero compliance violations detected on this revision node.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {findings.map((f) => {
                    const isNeedsVerif = f.triage_status === 'NEEDS_VERIFICATION' || f.triage_status === 'NEEDS_VERIFICATION_MISSING_EVIDENCE';
                    const isHumanRev = f.triage_status === 'ROUTED_TO_HUMAN_LOW_CONFIDENCE';

                    return (
                      <div
                        key={f.id}
                        style={{
                          padding: 12,
                          background: 'var(--glass-bg)',
                          borderRadius: 8,
                          borderLeft: `4px solid ${isNeedsVerif ? '#f59e0b' : f.severity === 'CRITICAL' ? '#ef4444' : f.severity === 'HIGH' ? '#f97316' : '#f59e0b'}`,
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, flexWrap: 'wrap', gap: 6 }}>
                          <span style={{ fontWeight: 700, fontSize: 12, color: 'var(--text-primary)' }}>
                            {f.issue_category} — <span style={{ color: f.severity === 'CRITICAL' ? '#f87171' : '#fbbf24' }}>{f.severity}</span>
                          </span>
                          <div style={{ display: 'flex', gap: 6 }}>
                            {isNeedsVerif && (
                              <span className="badge badge-warning" style={{ fontSize: 10, background: 'rgba(245,158,11,0.15)', color: '#fbbf24', border: '1px solid #f59e0b' }}>
                                Needs verification
                              </span>
                            )}
                            {isHumanRev && (
                              <span className="badge badge-secondary" style={{ fontSize: 10, background: 'rgba(148,163,184,0.15)', color: '#cbd5e1', border: '1px solid #64748b' }}>
                                Human review
                              </span>
                            )}
                            <span className="badge badge-info" style={{ fontSize: 10 }}>
                              {f.detector_source}
                            </span>
                          </div>
                        </div>

                        <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 6 }}>
                          {f.explanation_reason}
                        </div>

                        {/* Evidence Link / Citation Box */}
                        {f.evidence_source && (
                          <div style={{ marginBottom: 8, fontSize: 11, color: '#38bdf8', background: 'rgba(56,189,248,0.06)', padding: '4px 8px', borderRadius: 4, border: '1px solid rgba(56,189,248,0.15)' }}>
                            <span style={{ color: 'var(--text-muted)' }}>Evidence citation: </span>
                            {f.evidence_link ? (
                              <a href={f.evidence_link} target="_blank" rel="noreferrer" style={{ color: '#38bdf8', textDecoration: 'underline' }}>
                                {f.evidence_source}
                              </a>
                            ) : (
                              <span>{f.evidence_source}</span>
                            )}
                          </div>
                        )}

                        {f.suggested_correction && (
                          <div style={{ fontSize: 12, color: '#34d399', background: 'rgba(16,185,129,0.06)', padding: '6px 10px', borderRadius: 4, marginBottom: 8 }}>
                            Suggestion: "{f.suggested_correction}"
                          </div>
                        )}

                        {/* Creator Workflow Controls: Accept, Custom Edit, Reject with Rationale */}
                        {(role === 'CREATOR' || role === 'ADMINISTRATOR') && (
                          <div style={{ marginTop: 8 }}>
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                              {f.suggested_correction && (
                                <button
                                  className="btn btn-sm"
                                  style={{ background: 'var(--brand-600)', color: '#fff', fontSize: 11 }}
                                  onClick={() => handleResolveFinding(f, 'ACCEPT_SUGGESTION')}
                                  disabled={actionLoading}
                                >
                                  Accept Suggestion &amp; Commit v{revisions.length + 1}
                                </button>
                              )}
                              <button
                                className="btn btn-sm btn-secondary"
                                style={{ fontSize: 11 }}
                                onClick={() => {
                                  setActiveFindingEditId(activeFindingEditId === f.id ? null : f.id);
                                  setCustomEditText(f.suggested_correction || '');
                                }}
                                disabled={actionLoading}
                              >
                                {activeFindingEditId === f.id ? 'Cancel Custom Edit' : 'Custom Edit'}
                              </button>
                              <button
                                className="btn btn-sm btn-secondary"
                                style={{ fontSize: 11, color: '#f87171' }}
                                onClick={() => {
                                  setActiveFindingRejectId(activeFindingRejectId === f.id ? null : f.id);
                                  setRejectRationale('');
                                }}
                                disabled={actionLoading}
                              >
                                {activeFindingRejectId === f.id ? 'Cancel Rejection' : 'Reject with Rationale'}
                              </button>
                            </div>

                            {/* Inline Custom Edit Form */}
                            {activeFindingEditId === f.id && (
                              <div style={{ marginTop: 8, padding: 8, background: 'rgba(255,255,255,0.05)', borderRadius: 6, border: '1px solid var(--border-color)' }}>
                                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                                  Enter custom replacement text:
                                </div>
                                <input
                                  type="text"
                                  className="search-input"
                                  style={{ width: '100%', marginBottom: 6, fontSize: 12 }}
                                  value={customEditText}
                                  onChange={(e) => setCustomEditText(e.target.value)}
                                  placeholder="Type custom text..."
                                />
                                <button
                                  className="btn btn-sm btn-primary"
                                  style={{ fontSize: 11 }}
                                  disabled={!customEditText.trim() || actionLoading}
                                  onClick={() => handleResolveFinding(f, 'CUSTOM_EDIT', customEditText)}
                                >
                                  Commit Custom Edit &amp; v{revisions.length + 1}
                                </button>
                              </div>
                            )}

                            {/* Inline Reject with Rationale Form */}
                            {activeFindingRejectId === f.id && (
                              <div style={{ marginTop: 8, padding: 8, background: 'rgba(239,68,68,0.08)', borderRadius: 6, border: '1px solid rgba(239,68,68,0.2)' }}>
                                <div style={{ fontSize: 11, color: '#fca5a5', marginBottom: 4 }}>
                                  Provide justification/rationale for rejecting finding:
                                </div>
                                <input
                                  type="text"
                                  className="search-input"
                                  style={{ width: '100%', marginBottom: 6, fontSize: 12 }}
                                  value={rejectRationale}
                                  onChange={(e) => setRejectRationale(e.target.value)}
                                  placeholder="Reason for rejection (e.g. approved exception)..."
                                />
                                <button
                                  className="btn btn-sm"
                                  style={{ background: '#ef4444', color: '#fff', fontSize: 11 }}
                                  disabled={!rejectRationale.trim() || actionLoading}
                                  onClick={() => handleResolveFinding(f, 'REJECT_WITH_RATIONALE', undefined, rejectRationale)}
                                >
                                  Confirm Rejection &amp; Log Rationale
                                </button>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
