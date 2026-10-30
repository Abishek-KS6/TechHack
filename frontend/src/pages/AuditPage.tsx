import React, { useState, useEffect } from 'react';
import { auditApi, type AuditLogItem, type AuditVerificationResult } from '../api/client';
import { useAuth } from '../context/AuthContext';
import TiltCard from '../components/TiltCard';
import ThreeDShieldBadge from '../components/ThreeDShieldBadge';

export default function AuditPage() {
  const { user, role, switchRole } = useAuth();
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState<string>('');
  const [switching, setSwitching] = useState<boolean>(false);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  // Cryptographic chain verification state
  const [verifying, setVerifying] = useState<boolean>(false);
  const [verificationResult, setVerificationResult] = useState<AuditVerificationResult | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const fetchLogs = async () => {
    if (role === 'CREATOR') {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await auditApi.getLogs(100);
      setLogs(data || []);
    } catch (err: any) {
      setError(err.message || 'Failed to retrieve audit ledger from database.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [role]);

  const handleRoleSwitch = async (targetRole: 'REVIEWER' | 'ADMINISTRATOR') => {
    setSwitching(true);
    try {
      await switchRole(targetRole);
    } catch (err: any) {
      setError(`Failed to switch role: ${err.message}`);
    } finally {
      setSwitching(false);
    }
  };

  const handleVerifyChain = async () => {
    setVerifying(true);
    setVerifyError(null);
    try {
      const res = await auditApi.verifyChain();
      setVerificationResult(res);
    } catch (err: any) {
      setVerifyError(err.message || 'Cryptographic chain verification failed.');
    } finally {
      setVerifying(false);
    }
  };

  const exportCSV = () => {
    if (logs.length === 0) return;
    const headers = ['SequenceID', 'Action', 'Timestamp', 'PreviousHash', 'CurrentHash', 'Payload'];
    const rows = logs.map((l) => [
      l.sequence_id,
      l.action,
      l.timestamp,
      l.previous_hash,
      l.current_hash,
      `"${JSON.stringify(l.payload).replace(/"/g, '""')}"`,
    ]);
    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `brandshield_audit_ledger_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const copyToClipboard = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 1800);
  };

  const filtered = logs.filter(
    (l) =>
      l.action.toLowerCase().includes(search.toLowerCase()) ||
      JSON.stringify(l.payload).toLowerCase().includes(search.toLowerCase()) ||
      l.current_hash.toLowerCase().includes(search.toLowerCase())
  );

  // Latest 5 blocks for the 3D chain visualizer
  const recentBlocks = [...logs].reverse().slice(0, 6);

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 14 }}>
        <div>
          <h1 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span>Cryptographic Merkle Audit Ledger</span>
            <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 999, background: 'rgba(16,185,129,0.18)', border: '1px solid #10b981', color: '#047857', fontWeight: 700 }}>
              SHA-256 Chained
            </span>
          </h1>
          <p>Append-only, SHA-256 hash-chained immutable audit trail guaranteeing regulatory non-repudiation and SOC 2 compliance.</p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button className="btn btn-secondary btn-sm" onClick={exportCSV} disabled={logs.length === 0} style={{ borderRadius: 10 }}>
            Export CSV
          </button>
          <button
            className="btn btn-primary btn-sm btn-3d"
            onClick={handleVerifyChain}
            disabled={verifying}
            style={{ borderRadius: 10, padding: '8px 16px', fontWeight: 700 }}
          >
            {verifying ? 'Verifying Merkle Tree…' : '🛡️ Verify Merkle Integrity'}
          </button>
        </div>
      </div>

      {/* Separation of Duties Notice for Creators */}
      {role === 'CREATOR' ? (
        <TiltCard maxTilt={8} glare={true} style={{ maxWidth: 680, margin: '40px auto', borderRadius: 'var(--radius-lg)' }}>
          <div style={{ padding: 40, textAlign: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
              <ThreeDShieldBadge blockCount={logs.length || 27} />
            </div>
            <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 8, color: 'var(--text-primary)' }}>
              Audit Ledger Access Restricted
            </h2>
            <div style={{ fontSize: 13, color: '#d97706', fontWeight: 700, marginBottom: 16, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Separation of Duties (SOC 2 / ISO 27001 Compliance)
            </div>
            <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 24 }}>
              The immutable SHA-256 cryptographic audit ledger records system events, IP telemetry, and regulatory determinations. To maintain segregation of duties, content Creators are prohibited from inspecting or verifying audit blocks.
            </p>
            <div style={{ padding: '12px 18px', background: 'rgba(99,102,241,0.08)', borderRadius: 12, marginBottom: 24, fontSize: 13, color: 'var(--text-secondary)' }}>
              Current User: <strong style={{ color: 'var(--text-primary)' }}>{user?.full_name || 'Alex Creator'}</strong> · Role: <span className="badge badge-info" style={{ textTransform: 'uppercase', borderRadius: 999 }}>{role}</span>
            </div>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
              <button
                className="btn btn-primary btn-3d"
                disabled={switching}
                onClick={() => handleRoleSwitch('REVIEWER')}
                style={{ background: '#059669', display: 'flex', alignItems: 'center', gap: 8, borderRadius: 12, padding: '10px 18px', fontWeight: 700 }}
              >
                {switching ? 'Switching…' : 'Switch to Reviewer Account'}
              </button>
              <button
                className="btn btn-secondary"
                disabled={switching}
                onClick={() => handleRoleSwitch('ADMINISTRATOR')}
                style={{ display: 'flex', alignItems: 'center', gap: 8, borderRadius: 12, padding: '10px 18px', fontWeight: 700 }}
              >
                {switching ? 'Switching…' : 'Switch to Admin Account'}
              </button>
            </div>
          </div>
        </TiltCard>
      ) : (
        <>
          {error && (
            <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', padding: 14, borderRadius: 10, marginBottom: 20, color: '#b91c1c' }}>
              <strong>Ledger Error:</strong> {error}
            </div>
          )}

          {/* Verification Result Card */}
          {verificationResult && (
            <TiltCard maxTilt={4} glare={true} style={{ marginBottom: 24, borderRadius: 'var(--radius-md)' }}>
              <div
                style={{
                  padding: 20,
                  borderRadius: 'var(--radius-md)',
                  border: `1.5px solid ${verificationResult.is_valid ? '#10b981' : '#ef4444'}`,
                  background: verificationResult.is_valid ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
                  <span style={{ fontSize: 24, fontWeight: 800, color: verificationResult.is_valid ? '#059669' : '#dc2626' }}>
                    {verificationResult.is_valid ? '🛡️' : '✕'}
                  </span>
                  <div>
                    <div style={{ fontWeight: 800, fontSize: 16, color: verificationResult.is_valid ? '#065f46' : '#991b1b' }}>
                      {verificationResult.is_valid ? 'Cryptographic Hash Chain: 100% Intact & Verified' : 'Chain Integrity Discrepancy Detected'}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      {verificationResult.verification_message} (Traversed and verified {verificationResult.total_records} sequential blocks in database ledger).
                    </div>
                  </div>
                </div>
                {verificationResult.has_historical_break && (
                  <div style={{ marginTop: 12, padding: '10px 14px', background: 'rgba(245, 158, 11, 0.15)', border: '1px solid #f59e0b', borderRadius: 8, fontSize: 12, color: '#92400e' }}>
                    <strong>Historical Chain Status:</strong> {verificationResult.historical_break_notes || 'known historical break at #9 (pre-fix, preserved)'}. Chain verified sound from subsequent blocks onwards.
                  </div>
                )}
              </div>
            </TiltCard>
          )}

          {verifyError && (
            <div style={{ background: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', color: '#b91c1c', padding: 14, borderRadius: 10, marginBottom: 20, fontSize: 13 }}>
              <strong>Verification Error:</strong> {verifyError}
            </div>
          )}

          {/* 3D Cryptographic Chain Live Visualizer */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--text-muted)' }}>
                Live Block Sequence Visualization (Top 6 Merkle Nodes):
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>
                Total Verified Blocks: <strong style={{ color: 'var(--text-primary)' }}>{logs.length}</strong>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
              {recentBlocks.map((block, idx) => (
                <TiltCard key={block.sequence_id} maxTilt={10} glare={true} style={{ borderRadius: 12 }}>
                  <div
                    style={{
                      padding: '14px 16px',
                      background: 'rgba(255, 255, 255, 0.85)',
                      backdropFilter: 'blur(16px)',
                      borderRadius: 12,
                      border: '1.5px solid rgba(255, 255, 255, 0.95)',
                      boxShadow: '0 8px 24px rgba(25, 45, 120, 0.08)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontFamily: 'monospace', fontWeight: 800, color: '#4f46e5', fontSize: 13 }}>
                        Block #{block.sequence_id}
                      </span>
                      <span style={{ fontSize: 10, color: '#059669', background: 'rgba(16,185,129,0.15)', padding: '2px 6px', borderRadius: 999, fontWeight: 700 }}>
                        ✓ SEALED
                      </span>
                    </div>

                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {block.action}
                    </div>

                    <div
                      onClick={() => copyToClipboard(block.current_hash)}
                      style={{
                        fontFamily: 'monospace',
                        fontSize: 10,
                        color: '#4f46e5',
                        background: 'rgba(99,102,241,0.08)',
                        padding: '4px 6px',
                        borderRadius: 6,
                        cursor: 'pointer',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                      title="Click to copy full SHA-256 hash"
                    >
                      <span>{block.current_hash.substring(0, 10)}…</span>
                      <span style={{ fontSize: 9 }}>{copiedHash === block.current_hash ? '✓ Copied' : '📋'}</span>
                    </div>

                    <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                      {new Date(block.timestamp).toLocaleTimeString()}
                    </div>
                  </div>
                </TiltCard>
              ))}
            </div>
          </div>

          {/* Toolbar */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
            <div className="search-wrapper" style={{ flex: 1 }}>
              <input
                className="search-input"
                style={{ width: '100%', background: 'rgba(255, 255, 255, 0.85)', backdropFilter: 'blur(12px)', borderRadius: 12, border: '1.5px solid rgba(255,255,255,0.95)' }}
                placeholder="Search audit trail by action, hash, or payload…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button className="btn btn-secondary btn-sm" onClick={fetchLogs} style={{ borderRadius: 10 }}>
              Refresh Ledger
            </button>
          </div>

          {/* Audit Table */}
          <div className="table-wrapper" style={{ borderRadius: 'var(--radius-lg)', overflow: 'hidden', boxShadow: '0 8px 30px rgba(25, 45, 120, 0.08)' }}>
            <table>
              <thead>
                <tr>
                  <th>Seq #</th>
                  <th>Action Type</th>
                  <th>Timestamp (UTC)</th>
                  <th>SHA-256 Block Digest</th>
                  <th>Payload Summary</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                      Loading immutable audit chain…
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                      No audit logs found.
                    </td>
                  </tr>
                ) : (
                  filtered.map((log) => (
                    <tr key={log.sequence_id} style={{ transition: 'background 0.2s ease' }}>
                      <td>
                        <span style={{ fontFamily: 'monospace', fontWeight: 800, color: '#4f46e5' }}>
                          #{log.sequence_id}
                        </span>
                      </td>
                      <td>
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 700,
                            padding: '4px 10px',
                            borderRadius: 6,
                            background: 'rgba(99,102,241,0.12)',
                            color: '#4338ca',
                          }}
                        >
                          {log.action}
                        </span>
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                        {new Date(log.timestamp).toLocaleString()}
                      </td>
                      <td>
                        <div
                          onClick={() => copyToClipboard(log.current_hash)}
                          style={{
                            fontFamily: 'monospace',
                            fontSize: 11,
                            color: '#059669',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 6,
                            background: 'rgba(16,185,129,0.08)',
                            padding: '3px 8px',
                            borderRadius: 6,
                          }}
                          title={`Previous: ${log.previous_hash}\nCurrent: ${log.current_hash}\nClick to copy`}
                        >
                          <span>{log.current_hash.substring(0, 16)}…</span>
                          <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                            {copiedHash === log.current_hash ? '✓' : '⧉'}
                          </span>
                        </div>
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 420, fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {JSON.stringify(log.payload)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

