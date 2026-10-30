import React, { useState } from 'react';
import { analysisApi, submissionsApi, type FindingItem } from '../api/client';
import { useAuth } from '../context/AuthContext';
import TiltCard from '../components/TiltCard';

const SAMPLE_TEMPLATES = [
  {
    name: 'High-Violation Sample (Banned Terms & Absolutes)',
    text: 'Our next-generation trading platform delivers a 100% risk-free investment experience with foolproof algorithmic execution. It is the definitive cure for market volatility and ensures promised returns for all institutional clients.',
  },
  {
    name: 'Stale Fact Sample (Expired Substantiation)',
    text: 'Acme FinTech processes $4.2B in annualized volume across 25 global jurisdictions with 99.999% uptime, as certified in our 2023 Q1 compliance review.',
  },
  {
    name: 'Compliant B2B Sample (Certified Copy)',
    text: 'Acme FinTech™ provides institutionally hedged digital asset infrastructure with high-throughput settlement. Investments are subject to market risk and past performance is not indicative of future results.',
  },
];

export default function AnalysisPage() {
  const { activeBrandProfileId, token } = useAuth();
  const [text, setText] = useState<string>(SAMPLE_TEMPLATES[0].text);
  const [provider, setProvider] = useState<string>('Azure OpenAI');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [findings, setFindings] = useState<FindingItem[] | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  // SSE Streaming state
  const [streaming, setStreaming] = useState<boolean>(false);
  const [stages, setStages] = useState<Record<string, { latency_ms?: number; status: string }>>({});

  const runLiveAnalysis = async () => {
    if (!text.trim()) {
      setError('Please enter document content to analyze.');
      return;
    }
    setLoading(true);
    setError(null);
    setFindings(null);
    const start = performance.now();
    try {
      const res = await analysisApi.analyzeLive(text, activeBrandProfileId, provider);
      const end = performance.now();
      setLatencyMs(res.latency_ms || Math.round(end - start));
      setFindings(res.findings || []);
    } catch (err: any) {
      setError(err.message || 'Analysis failed to execute on backend engine.');
    } finally {
      setLoading(false);
    }
  };

  const runSSEStreamingAnalysis = async () => {
    if (!text.trim()) {
      setError('Please enter document content to analyze.');
      return;
    }
    setStreaming(true);
    setError(null);
    setStages({});
    setFindings([]);

    try {
      const sub = await submissionsApi.submitText(
        `Stream Analysis - ${new Date().toLocaleTimeString()}`,
        activeBrandProfileId,
        text
      );

      const baseUrl = (import.meta.env.VITE_API_URL as string) || '/api/v1';
      const eventSource = new EventSource(
        `${baseUrl}/submissions/${sub.id}/analyze/stream?token=${encodeURIComponent(token || '')}`
      );

      eventSource.addEventListener('STAGE_1_DETERMINISTIC_COMPLETE', (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        setStages((prev) => ({
          ...prev,
          stage1: { latency_ms: data.latency_ms, status: `Complete (${data.findings_count} hits)` },
        }));
      });

      eventSource.addEventListener('STAGE_2_TEMPORAL_FACT_RAG_COMPLETE', (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        setStages((prev) => ({
          ...prev,
          stage2: { latency_ms: data.latency_ms, status: `Complete (${data.stale_facts} stale facts)` },
        }));
      });

      eventSource.addEventListener('STAGE_3_PRIVACY_GATE_VERIFIED', (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        setStages((prev) => ({
          ...prev,
          stage3: { latency_ms: data.latency_ms, status: `Verified (${data.provider})` },
        }));
      });

      eventSource.addEventListener('STAGE_4_TRIAGE_COMPLETE', (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        setStages((prev) => ({
          ...prev,
          stage4: { latency_ms: data.latency_ms, status: `Triaged (${data.total_findings} total findings)` },
        }));
      });

      eventSource.addEventListener('PIPELINE_COMPLETE', (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        setFindings(data.findings || []);
        setLatencyMs(data.duration_ms);
        setStreaming(false);
        eventSource.close();
      });

      eventSource.addEventListener('PIPELINE_ERROR', (e: MessageEvent) => {
        const data = JSON.parse(e.data);
        setError(data.error || 'Pipeline encountered an error during streaming.');
        setStreaming(false);
        eventSource.close();
      });

      eventSource.onerror = () => {
        setStreaming(false);
        eventSource.close();
      };
    } catch (err: any) {
      setError(err.message || 'Failed to initialize streaming pipeline.');
      setStreaming(false);
    }
  };

  const sevColor: Record<string, string> = {
    CRITICAL: '#ef4444',
    HIGH: '#f97316',
    MEDIUM: '#f59e0b',
    LOW: '#3b82f6',
  };

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span>Brand Compliance &amp; Verification Engine</span>
            <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 999, background: 'rgba(99,102,241,0.18)', border: '1px solid #6366f1', color: '#4338ca', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              3D Neural AST
            </span>
          </h1>
          <p>Verify content against active brand guidelines, factual records, and compliance rules in real-time.</p>
        </div>
      </div>

      {error && (
        <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', padding: 14, borderRadius: 10, marginBottom: 20, color: '#b91c1c' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Preset Selector */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', alignSelf: 'center', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>Quick Samples:</span>
        {SAMPLE_TEMPLATES.map((tmpl) => (
          <button
            key={tmpl.name}
            className="btn btn-secondary btn-sm"
            style={{
              fontSize: 12,
              fontWeight: 600,
              backdropFilter: 'blur(10px)',
              borderRadius: 999,
              padding: '6px 14px',
              transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
            onClick={() => {
              setText(tmpl.text);
              setFindings(null);
            }}
          >
            {tmpl.name}
          </button>
        ))}
      </div>

      <div className="grid-2" style={{ gridTemplateColumns: '1.2fr 1fr', alignItems: 'start', gap: 24 }}>
        {/* Input Panel */}
        <div>
          <TiltCard maxTilt={5} glare={true} style={{ marginBottom: 20, borderRadius: 'var(--radius-lg)' }}>
            <div style={{ padding: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div className="card-title" style={{ fontSize: 16, fontWeight: 700 }}>
                  Content Copy Under Review
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', display: 'inline-block' }} />
                  Live AST Parser
                </div>
              </div>

              <div className={`scanner-3d-box ${loading || streaming ? 'active' : ''}`} style={{ position: 'relative', borderRadius: 14 }}>
                {(loading || streaming) && <div className="scanner-beam-line" />}
                <textarea
                  className="form-input"
                  style={{
                    minHeight: 200,
                    width: '100%',
                    fontFamily: 'Inter, sans-serif',
                    fontSize: 14,
                    lineHeight: 1.6,
                    background: 'rgba(255, 255, 255, 0.85)',
                    backdropFilter: 'blur(16px)',
                    border: '1.5px solid rgba(255, 255, 255, 0.95)',
                    borderRadius: 14,
                    padding: 16,
                  }}
                  placeholder="Paste marketing copy, legal disclaimer, or campaign brief here…"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 18, flexWrap: 'wrap', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>Inference Engine:</span>
                  <select
                    className="form-select"
                    style={{ padding: '8px 12px', fontSize: 12, borderRadius: 10, background: 'rgba(255,255,255,0.9)', fontWeight: 600 }}
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                  >
                    <option value="Azure OpenAI">Azure OpenAI (Zero-Retention)</option>
                    <option value="Anthropic">Anthropic Claude (VPC Sandbox)</option>
                  </select>
                </div>

                <div style={{ display: 'flex', gap: 10 }}>
                  <button
                    className="btn btn-primary btn-3d"
                    onClick={runLiveAnalysis}
                    disabled={loading || streaming}
                    style={{ padding: '9px 18px', fontSize: 13, fontWeight: 700, borderRadius: 12 }}
                  >
                    {loading ? 'Scanning AST…' : '⚡ 3D Laser Scan'}
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={runSSEStreamingAnalysis}
                    disabled={loading || streaming}
                    style={{ padding: '9px 14px', fontSize: 13, fontWeight: 600, borderRadius: 12 }}
                  >
                    {streaming ? 'Streaming…' : 'Stream Pipeline'}
                  </button>
                </div>
              </div>
            </div>
          </TiltCard>

          {/* SSE Stage Tracker (when streaming active) */}
          {(streaming || Object.keys(stages).length > 0) && (
            <TiltCard maxTilt={4} glare={false} style={{ marginBottom: 20 }}>
              <div style={{ padding: 20 }}>
                <div className="card-title" style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>Multistage Verification Cascade</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {[
                    { key: 'stage1', label: 'Stage 1: Aho-Corasick Deterministic Engine', tag: 'Fast String AST' },
                    { key: 'stage2', label: 'Stage 2: Temporal Fact Grounding & Hybrid RAG', tag: 'Temporal Index' },
                    { key: 'stage3', label: 'Stage 3: Privacy-Gated Boundary & SLA Watchdog', tag: 'Data Perimeter' },
                    { key: 'stage4', label: 'Stage 4: Calibrated Triage & Automation Bias Guard', tag: 'Human Alignment' },
                  ].map((s) => {
                    const stageInfo = stages[s.key];
                    return (
                      <div
                        key={s.key}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '10px 14px',
                          background: 'rgba(255, 255, 255, 0.65)',
                          backdropFilter: 'blur(12px)',
                          borderRadius: 10,
                          border: stageInfo ? '1.5px solid #10b981' : '1px solid var(--glass-border)',
                          boxShadow: stageInfo ? '0 4px 12px rgba(16,185,129,0.15)' : 'none',
                          transition: 'all 0.3s ease',
                        }}
                      >
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{s.label}</span>
                          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{s.tag}</span>
                        </div>
                        <span style={{ fontSize: 11, fontWeight: 700, color: stageInfo ? '#059669' : 'var(--text-muted)' }}>
                          {stageInfo ? `✓ ${stageInfo.status} (${stageInfo.latency_ms?.toFixed(1) || '<1'}ms)` : 'Waiting…'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </TiltCard>
          )}
        </div>

        {/* Results Panel */}
        <div>
          <TiltCard maxTilt={4} glare={true} style={{ borderRadius: 'var(--radius-lg)' }}>
            <div style={{ padding: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
                <div className="card-title" style={{ fontSize: 16, fontWeight: 700 }}>
                  Verification Findings &amp; Triage
                </div>
                {latencyMs !== null && (
                  <span className="badge badge-success" style={{ fontSize: 11, fontWeight: 700, padding: '4px 10px', borderRadius: 999 }}>
                    ⚡ {latencyMs} ms latency
                  </span>
                )}
              </div>

              {loading && (
                <div style={{ textAlign: 'center', padding: '50px 0', color: 'var(--text-muted)' }}>
                  <div style={{ width: 44, height: 44, borderRadius: '50%', border: '3px solid rgba(99,102,241,0.2)', borderTopColor: '#4f46e5', margin: '0 auto 16px', animation: 'spin 0.8s linear infinite' }} />
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Scanning AST against corporate brand guidelines &amp; approved facts…</div>
                  <div style={{ fontSize: 12, marginTop: 6 }}>Calculating cosine embeddings and temporal staleness</div>
                </div>
              )}

              {!loading && findings === null && (
                <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>
                  <div style={{ fontSize: 36, marginBottom: 12, opacity: 0.7 }}>🔍</div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>Ready for Inspection</div>
                  <div style={{ fontSize: 13 }}>Click "3D Laser Scan" or choose a quick test sample to evaluate compliance.</div>
                </div>
              )}

              {!loading && findings !== null && findings.length === 0 && (
                <div style={{ textAlign: 'center', padding: '40px 24px', background: 'rgba(16,185,129,0.12)', borderRadius: 16, border: '1.5px solid rgba(16,185,129,0.3)', boxShadow: '0 8px 24px rgba(16,185,129,0.1)' }}>
                  <div style={{ fontSize: 42, color: '#059669', marginBottom: 10 }}>✓</div>
                  <div style={{ fontSize: 18, fontWeight: 800, color: '#065f46', marginBottom: 6 }}>
                    Verified 100% Compliant
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    Zero terminology breaches, tone deviations, or stale factual statements detected. Ready for immediate deployment.
                  </div>
                </div>
              )}

              {!loading && findings !== null && findings.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    Detected {findings.length} Compliance Findings:
                  </div>

                  {findings.map((f, idx) => {
                    const isNeedsVerification = f.triage_status === 'NEEDS_VERIFICATION' || f.triage_status === 'NEEDS_VERIFICATION_MISSING_EVIDENCE';
                    const isHumanReview = f.triage_status === 'ROUTED_TO_HUMAN_LOW_CONFIDENCE';
                    const isFlagged = f.triage_status === 'FLAGGED_HIGH_CONFIDENCE';
                    const isStale = f.triage_status === 'STALE_FACT_REVERIFY';
                    const accentColor = sevColor[f.severity] || '#f59e0b';

                    return (
                      <div
                        key={f.id || idx}
                        style={{
                          padding: 16,
                          background: 'rgba(255, 255, 255, 0.85)',
                          backdropFilter: 'blur(16px)',
                          borderRadius: 14,
                          borderLeft: `5px solid ${accentColor}`,
                          borderTop: '1px solid rgba(255, 255, 255, 0.95)',
                          borderRight: '1px solid rgba(255, 255, 255, 0.8)',
                          borderBottom: '1.5px solid rgba(200, 215, 255, 0.5)',
                          boxShadow: '0 6px 20px rgba(25, 45, 120, 0.06)',
                          transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 6 }}>
                          <span style={{ fontWeight: 800, fontSize: 13, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span>{f.issue_category}</span>
                            <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, background: `${accentColor}20`, color: accentColor, fontWeight: 800 }}>
                              {f.severity}
                            </span>
                          </span>

                          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            {isNeedsVerification && (
                              <span className="badge badge-warning" style={{ fontSize: 10, background: 'rgba(245,158,11,0.18)', color: '#b45309', border: '1px solid #f59e0b' }}>
                                Needs verification
                              </span>
                            )}
                            {isHumanReview && (
                              <span className="badge badge-secondary" style={{ fontSize: 10, background: 'rgba(148,163,184,0.2)', color: '#334155', border: '1px solid #94a3b8' }}>
                                Routed to human
                              </span>
                            )}
                            {isFlagged && (
                              <span className="badge badge-danger" style={{ fontSize: 10, background: 'rgba(239,68,68,0.18)', color: '#b91c1c', border: '1px solid #ef4444' }}>
                                Flagged
                              </span>
                            )}
                            {isStale && (
                              <span className="badge badge-warning" style={{ fontSize: 10, background: 'rgba(245,158,11,0.18)', color: '#b45309', border: '1px solid #f59e0b' }}>
                                Stale fact
                              </span>
                            )}
                            <span className="badge badge-info" style={{ fontSize: 10, borderRadius: 999 }}>
                              {f.detector_source}
                            </span>
                          </div>
                        </div>

                        <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.5, fontWeight: 500 }}>
                          {f.explanation_reason}
                        </div>

                        {f.suggested_correction && (
                          <div
                            style={{
                              fontSize: 12,
                              color: '#065f46',
                              background: 'rgba(16,185,129,0.12)',
                              padding: '8px 12px',
                              borderRadius: 8,
                              border: '1px solid rgba(16,185,129,0.25)',
                              marginBottom: 8,
                            }}
                          >
                            <strong style={{ color: '#047857' }}>Suggested Replacement:</strong> "{f.suggested_correction}"
                          </div>
                        )}

                        {/* Evidence Link / Citation Box */}
                        {f.evidence_source && (
                          <div style={{ marginBottom: 10, fontSize: 11, color: '#0369a1', display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(56,189,248,0.12)', padding: '6px 10px', borderRadius: 6, border: '1px solid rgba(56,189,248,0.25)' }}>
                            <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Evidence citation:</span>
                            {f.evidence_link ? (
                              <a href={f.evidence_link} target="_blank" rel="noreferrer" style={{ color: '#0284c7', textDecoration: 'underline', fontWeight: 600 }}>
                                {f.evidence_source}
                              </a>
                            ) : (
                              <span style={{ fontWeight: 600 }}>{f.evidence_source}</span>
                            )}
                          </div>
                        )}

                        {/* 3D Confidence Probability Meter */}
                        <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(0,0,0,0.06)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                            <span>Confidence Calibrator: <strong style={{ color: 'var(--text-primary)' }}>{Math.round(f.confidence_score * 100)}%</strong></span>
                            <span>{f.is_automation_bias_audit ? '🛡️ Bias Guard Active' : 'Calibrated'}</span>
                          </div>
                          <div style={{ height: 5, background: 'rgba(0,0,0,0.06)', borderRadius: 999, overflow: 'hidden' }}>
                            <div
                              style={{
                                width: `${Math.round(f.confidence_score * 100)}%`,
                                height: '100%',
                                background: `linear-gradient(90deg, #6366f1, ${accentColor})`,
                                borderRadius: 999,
                                transition: 'width 0.4s ease',
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </TiltCard>
        </div>
      </div>
    </div>
  );
}

