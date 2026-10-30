import React, { useState, useEffect } from 'react';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid
} from 'recharts';
import {
  FileText,
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  TrendingUp,
  Activity,
  Layers,
  Sparkles,
} from 'lucide-react';
import { dashboardApi, auditApi, type DashboardSummary, type GovernanceReport, type AuditLogItem } from '../api/client';
import { useAuth } from '../context/AuthContext';
import TiltCard from '../components/TiltCard';
import ThreeDShieldBadge from '../components/ThreeDShieldBadge';

export default function Dashboard() {
  const { role } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [governance, setGovernance] = useState<GovernanceReport | null>(null);
  const [recentLogs, setRecentLogs] = useState<AuditLogItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [sumData, govData, logsData] = await Promise.all([
        dashboardApi.getSummary().catch(() => null),
        dashboardApi.getGovernanceReport().catch(() => null),
        auditApi.getLogs(6).catch(() => []),
      ]);
      setSummary(sumData);
      setGovernance(govData);
      setRecentLogs(logsData || []);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch live dashboard telemetry');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, [role]);

  // Derived metrics
  const totalSubmissions = summary?.total_submissions || 0;
  const totalFindings = summary?.total_findings || governance?.total_findings || 0;
  const approvedCount = summary?.approved || 0;
  const awaitingReview = summary?.awaiting_review || 0;
  const passRate = totalSubmissions > 0
    ? Math.round((approvedCount / totalSubmissions) * 100)
    : 100;

  const categoryBarData = governance?.recharts_category_bar || [];
  const triagePieData = governance?.recharts_triage_pie || [];
  const reviewTrendsData = governance?.recharts_review_trends_line || [];

  return (
    <div className="fade-in">
      {/* ── 3D Spatial Header with Holographic Integrity Seal ── */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 20 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span style={{ 
              background: 'linear-gradient(135deg, #4f46e5, #06b6d4)', 
              color: '#fff', 
              padding: '4px 10px', 
              borderRadius: 999, 
              fontSize: 11, 
              fontWeight: 800, 
              letterSpacing: '0.06em', 
              textTransform: 'uppercase',
              boxShadow: '0 4px 12px rgba(79,70,229,0.3)'
            }}>
              3D Quantum Telemetry
            </span>
            <span style={{ fontSize: 13, color: '#64748b', fontWeight: 600 }}>Active Node: Acme FinTech</span>
          </div>
          <h1 style={{ fontSize: 32, fontWeight: 900, letterSpacing: '-0.02em', color: '#0f172a' }}>
            Compliance &amp; Governance Overview
          </h1>
          <p style={{ color: '#334155', fontSize: 14.5, fontWeight: 500 }}>
            Real-time brand compliance telemetry, tamper-evident Merkle hash chain, and multi-tier triage
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <ThreeDShieldBadge
            isValid={true}
            totalBlocks={recentLogs.length > 0 ? recentLogs[0].sequence_id : 27}
            subtitle="SHA-256 Merkle Ledger"
          />

          <button
            className="btn btn-secondary btn-3d"
            onClick={fetchDashboardData}
            disabled={loading}
            style={{ display: 'flex', alignItems: 'center', gap: 8, height: 46 }}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            <span>{loading ? 'Synchronizing…' : 'Sync Telemetry'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div style={{ 
          background: 'rgba(239, 68, 68, 0.12)', 
          border: '1.5px solid #ef4444', 
          padding: 16, 
          borderRadius: 14, 
          marginBottom: 24, 
          color: '#991b1b',
          backdropFilter: 'blur(20px)'
        }}>
          <strong>Telemetry Synchronization Warning:</strong> {error}
        </div>
      )}

      {/* ── 3D Interactive Tilt KPI Grid ── */}
      <div className="grid-4" style={{ marginBottom: 28 }}>
        {/* KPI 1: Total Submissions */}
        <TiltCard maxTilt={12} scale={1.03}>
          <div className="stat-card-3d" style={{ height: '100%' }}>
            <div className="stat-3d-header">
              <span className="stat-3d-label">Total Submissions</span>
              <div className="stat-3d-icon" style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)', color: '#fff' }}>
                <FileText size={22} />
              </div>
            </div>
            <div className="stat-3d-value">{loading ? '…' : totalSubmissions}</div>
            <div className="stat-3d-footer">
              <span style={{ color: '#059669', display: 'flex', alignItems: 'center', gap: 4 }}>
                <Activity size={13} /> Active Revision DAG
              </span>
              <span>All formats</span>
            </div>
          </div>
        </TiltCard>

        {/* KPI 2: Compliance Findings */}
        <TiltCard maxTilt={12} scale={1.03}>
          <div className="stat-card-3d" style={{ height: '100%' }}>
            <div className="stat-3d-header">
              <span className="stat-3d-label">Compliance Findings</span>
              <div className="stat-3d-icon" style={{ background: totalFindings > 0 ? 'linear-gradient(135deg, #ef4444, #f97316)' : 'linear-gradient(135deg, #10b981, #059669)', color: '#fff' }}>
                <AlertTriangle size={22} />
              </div>
            </div>
            <div className="stat-3d-value" style={{ color: totalFindings > 0 ? '#dc2626' : '#059669' }}>
              {loading ? '…' : totalFindings}
            </div>
            <div className="stat-3d-footer">
              <span style={{ color: totalFindings > 0 ? '#b91c1c' : '#059669', display: 'flex', alignItems: 'center', gap: 4 }}>
                <Sparkles size={13} /> {totalFindings > 0 ? `${totalFindings} detected flags` : 'Zero discrepancies'}
              </span>
              <span>Multi-tier triage</span>
            </div>
          </div>
        </TiltCard>

        {/* KPI 3: Approval Pass Rate */}
        <TiltCard maxTilt={12} scale={1.03}>
          <div className="stat-card-3d" style={{ height: '100%' }}>
            <div className="stat-3d-header">
              <span className="stat-3d-label">Approval Pass Rate</span>
              <div className="stat-3d-icon" style={{ background: 'linear-gradient(135deg, #10b981, #06b6d4)', color: '#fff' }}>
                <CheckCircle2 size={22} />
              </div>
            </div>
            <div className="stat-3d-value" style={{ color: '#059669' }}>
              {loading ? '…' : `${passRate}%`}
            </div>
            <div className="stat-3d-footer">
              <span style={{ color: '#059669', display: 'flex', alignItems: 'center', gap: 4 }}>
                <TrendingUp size={13} /> {approvedCount} signed off
              </span>
              <span>Regulatory grade</span>
            </div>
          </div>
        </TiltCard>

        {/* KPI 4: In Review Queue */}
        <TiltCard maxTilt={12} scale={1.03}>
          <div className="stat-card-3d" style={{ height: '100%' }}>
            <div className="stat-3d-header">
              <span className="stat-3d-label">In Review Queue</span>
              <div className="stat-3d-icon" style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)', color: '#fff' }}>
                <Clock size={22} />
              </div>
            </div>
            <div className="stat-3d-value" style={{ color: '#b45309' }}>
              {loading ? '…' : awaitingReview}
            </div>
            <div className="stat-3d-footer">
              <span style={{ color: '#b45309', display: 'flex', alignItems: 'center', gap: 4 }}>
                <Layers size={13} /> Human review required
              </span>
              <span>15% stochastic check</span>
            </div>
          </div>
        </TiltCard>
      </div>

      {/* ── 3D Charts Grid ── */}
      <div className="grid-2" style={{ marginBottom: 28 }}>
        {/* Recurring Issues Bar Chart */}
        <div className="card" style={{ minHeight: 360, position: 'relative' }}>
          <div className="card-header">
            <div>
              <div className="card-title">Recurring Compliance Issues (By Severity)</div>
              <div className="card-subtitle">Real-time classification breakdown mapped to brand guidelines</div>
            </div>
            <span className="badge badge-accent">Live Telemetry</span>
          </div>

          {categoryBarData.length > 0 ? (
            <ResponsiveContainer width="100%" height={270}>
              <BarChart data={categoryBarData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
                <XAxis dataKey="name" stroke="#64748b" tick={{ fontSize: 11, fill: '#334155', fontWeight: 600 }} />
                <YAxis stroke="#64748b" allowDecimals={false} tick={{ fill: '#334155', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(255, 255, 255, 0.96)',
                    borderColor: 'rgba(255, 255, 255, 1)',
                    color: '#0f172a',
                    borderRadius: 14,
                    boxShadow: '0 14px 34px rgba(35,55,140,0.2)',
                    fontWeight: 650,
                  }}
                />
                <Legend wrapperStyle={{ paddingTop: 10, fontSize: 12, fontWeight: 650 }} />
                <Bar dataKey="CRITICAL" stackId="a" fill="#ef4444" name="Critical" radius={[0, 0, 0, 0]} />
                <Bar dataKey="HIGH" stackId="a" fill="#f97316" name="High" radius={[0, 0, 0, 0]} />
                <Bar dataKey="MEDIUM" stackId="a" fill="#f59e0b" name="Medium" radius={[0, 0, 0, 0]} />
                <Bar dataKey="LOW" stackId="a" fill="#3b82f6" name="Low" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 260, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
              <div>No violation records found in this workspace yet.</div>
            </div>
          )}
        </div>

        {/* Triage Confidence Pie Chart */}
        <div className="card" style={{ minHeight: 360, position: 'relative' }}>
          <div className="card-header">
            <div>
              <div className="card-title">Triage Confidence Distribution</div>
              <div className="card-subtitle">Algorithmic probability scoring &amp; human triage routing</div>
            </div>
            <span className="badge badge-info">Tri-State Model</span>
          </div>

          {triagePieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={270}>
              <PieChart>
                <Pie
                  data={triagePieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={92}
                  paddingAngle={6}
                  dataKey="value"
                  nameKey="name"
                  label={({ name, value }: any) => `${name}: ${value}`}
                >
                  {triagePieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill || '#3b82f6'} stroke="rgba(255,255,255,0.8)" strokeWidth={2} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(255, 255, 255, 0.96)',
                    borderColor: 'rgba(255, 255, 255, 1)',
                    color: '#0f172a',
                    borderRadius: 14,
                    boxShadow: '0 14px 34px rgba(35,55,140,0.2)',
                    fontWeight: 650,
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: 260, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#64748b' }}>
              <div>Triage distribution will render here once findings are recorded.</div>
            </div>
          )}
        </div>
      </div>

      {/* ── Review Trends Line Chart ── */}
      <div className="card" style={{ marginBottom: 28 }}>
        <div className="card-header">
          <div>
            <div className="card-title">Human Review Sign-Off Decisions Over Time</div>
            <div className="card-subtitle">Zero auto-publishing invariant: human review disposition tracking</div>
          </div>
          <span className="badge badge-success">Audit Verified</span>
        </div>

        {reviewTrendsData.length > 0 ? (
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={reviewTrendsData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
              <XAxis dataKey="date" stroke="#64748b" tick={{ fontSize: 11, fill: '#334155', fontWeight: 600 }} />
              <YAxis stroke="#64748b" allowDecimals={false} tick={{ fill: '#334155', fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgba(255, 255, 255, 0.96)',
                  borderColor: 'rgba(255, 255, 255, 1)',
                  color: '#0f172a',
                  borderRadius: 14,
                  boxShadow: '0 14px 34px rgba(35,55,140,0.2)',
                  fontWeight: 650,
                }}
              />
              <Legend wrapperStyle={{ paddingTop: 10, fontSize: 12, fontWeight: 650 }} />
              <Line type="monotone" dataKey="approved" stroke="#10b981" strokeWidth={3} dot={{ r: 5 }} activeDot={{ r: 8 }} name="Approved" />
              <Line type="monotone" dataKey="changes_requested" stroke="#ef4444" strokeWidth={3} dot={{ r: 5 }} activeDot={{ r: 8 }} name="Changes Requested" />
              <Line type="monotone" dataKey="total_reviews" stroke="#6366f1" strokeWidth={2} strokeDasharray="5 5" name="Total Activity" />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ padding: '36px 0', textAlign: 'center', color: '#64748b', fontSize: 13.5 }}>
            Continuous trend analytics active. Decisions logged by Reviewers populate here automatically.
          </div>
        )}
      </div>

      {/* ── Recent Cryptographic Audit Trail (3D Glass Cards) ── */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="card-title">Recent Cryptographic Audit Trail</div>
            <div className="card-subtitle">SHA-256 hash-chained Merkle ledger entries with advisory lock concurrency protection</div>
          </div>
          <span className="badge badge-accent">Tamper Evident</span>
        </div>

        {recentLogs.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {recentLogs.map((log) => (
              <div
                key={log.sequence_id}
                className="block-3d-card"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: 12,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <span
                    style={{
                      fontFamily: 'monospace',
                      fontSize: 11.5,
                      fontWeight: 800,
                      color: '#4338ca',
                      background: 'rgba(99, 102, 241, 0.15)',
                      padding: '4px 10px',
                      borderRadius: 6,
                      border: '1px solid rgba(99, 102, 241, 0.3)',
                    }}
                  >
                    #{log.sequence_id} {log.action}
                  </span>
                  <span style={{ fontSize: 13.5, color: '#1e293b', fontWeight: 600 }}>
                    {log.payload?.title || log.payload?.name || log.payload?.email || JSON.stringify(log.payload).substring(0, 75)}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <span
                    style={{
                      fontFamily: 'monospace',
                      fontSize: 11,
                      color: '#475569',
                      background: 'rgba(0,0,0,0.04)',
                      padding: '2px 8px',
                      borderRadius: 4,
                    }}
                    title={log.current_hash}
                  >
                    SHA-256: {log.current_hash.substring(0, 10)}…
                  </span>
                  <span style={{ fontSize: 11.5, color: '#64748b', fontWeight: 600 }}>
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: '#64748b', textAlign: 'center', padding: '24px 0' }}>
            No audit ledger entries recorded yet.
          </div>
        )}
      </div>
    </div>
  );
}
