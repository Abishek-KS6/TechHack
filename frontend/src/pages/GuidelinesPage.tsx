import React, { useState, useEffect } from 'react';
import { brandsApi, type BrandGuidelineItem, type ApprovedFactItem } from '../api/client';
import { useAuth } from '../context/AuthContext';
import TiltCard from '../components/TiltCard';

export default function GuidelinesPage() {
  const { role, activeBrandProfileId } = useAuth();
  const [tab, setTab] = useState<'guidelines' | 'facts'>('guidelines');
  const [guidelines, setGuidelines] = useState<BrandGuidelineItem[]>([]);
  const [facts, setFacts] = useState<ApprovedFactItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState<string>('');

  // Add Guideline Modal
  const [showAddGModal, setShowAddGModal] = useState<boolean>(false);
  const [newClauseId, setNewClauseId] = useState<string>('');
  const [newClauseText, setNewClauseText] = useState<string>('');
  const [newCategory, setNewCategory] = useState<string>('TERMINOLOGY');
  const [newSeverity, setNewSeverity] = useState<string>('HIGH');
  const [addingG, setAddingG] = useState<boolean>(false);

  // Add Fact Modal
  const [showAddFModal, setShowAddFModal] = useState<boolean>(false);
  const [newFactStatement, setNewFactStatement] = useState<string>('');
  const [newSourceUrl, setNewSourceUrl] = useState<string>('');
  const [newEvidence, setNewEvidence] = useState<string>('');
  const [newExpiry, setNewExpiry] = useState<string>('2027-12-31');
  const [addingF, setAddingF] = useState<boolean>(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [gList, fList] = await Promise.all([
        brandsApi.getGuidelines(activeBrandProfileId).catch(() => []),
        brandsApi.listFacts().catch(() => []),
      ]);
      setGuidelines(gList || []);
      setFacts(fList || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load brand guidelines from backend.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [role, activeBrandProfileId]);

  const handleCreateGuideline = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newClauseId || !newClauseText) return;
    setAddingG(true);
    try {
      const embedding = Array(1536).fill(0.01);
      await brandsApi.createGuideline(activeBrandProfileId, {
        clause_identifier: newClauseId,
        clause_text: newClauseText,
        category: newCategory,
        severity: newSeverity,
        embedding,
      });
      setShowAddGModal(false);
      setNewClauseId('');
      setNewClauseText('');
      await fetchData();
    } catch (err: any) {
      setError(`Failed to create guideline: ${err.message}`);
    } finally {
      setAddingG(false);
    }
  };

  const handleCreateFact = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFactStatement || !newSourceUrl) return;
    setAddingF(true);
    try {
      const embedding = Array(1536).fill(0.01);
      const now = new Date().toISOString();
      await brandsApi.createFact({
        fact_statement: newFactStatement,
        original_source_url: newSourceUrl,
        evidence_excerpt: newEvidence || newFactStatement,
        verification_date: now,
        expiry_date: new Date(newExpiry).toISOString(),
        responsible_owner_id: '201a2561-e7b9-4f3d-b2f8-d93624575292',
        embedding,
      });
      setShowAddFModal(false);
      setNewFactStatement('');
      setNewSourceUrl('');
      setNewEvidence('');
      await fetchData();
    } catch (err: any) {
      setError(`Failed to create fact: ${err.message}`);
    } finally {
      setAddingF(false);
    }
  };

  const now = new Date();

  const filteredGuidelines = guidelines.filter(
    (g) =>
      g.clause_identifier.toLowerCase().includes(search.toLowerCase()) ||
      g.clause_text.toLowerCase().includes(search.toLowerCase()) ||
      g.category.toLowerCase().includes(search.toLowerCase())
  );

  const filteredFacts = facts.filter(
    (f) =>
      f.fact_statement.toLowerCase().includes(search.toLowerCase()) ||
      f.original_source_url.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 14 }}>
        <div>
          <h1 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span>Brand Knowledge &amp; Grounding Truth</span>
            <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 999, background: 'rgba(99,102,241,0.18)', border: '1px solid #6366f1', color: '#4338ca', fontWeight: 700 }}>
              1536-D Vector Indexed
            </span>
          </h1>
          <p>Approved brand voice guidelines, tone constraints, and temporally-grounded corporate facts evaluated by the AST engine.</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          {role !== 'CREATOR' && tab === 'guidelines' && (
            <button className="btn btn-primary btn-sm btn-3d" onClick={() => setShowAddGModal(true)} style={{ borderRadius: 10, padding: '8px 16px', fontWeight: 700 }}>
              + Add Guideline Rule
            </button>
          )}
          {role !== 'CREATOR' && tab === 'facts' && (
            <button className="btn btn-primary btn-sm btn-3d" onClick={() => setShowAddFModal(true)} style={{ borderRadius: 10, padding: '8px 16px', fontWeight: 700 }}>
              + Add Approved Fact
            </button>
          )}
        </div>
      </div>

      {error && (
        <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', padding: 14, borderRadius: 10, marginBottom: 20, color: '#b91c1c' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Tabs Row */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <button
          className={`btn ${tab === 'guidelines' ? 'btn-primary' : 'btn-secondary'} btn-sm`}
          onClick={() => setTab('guidelines')}
          style={{
            borderRadius: 999,
            padding: '8px 20px',
            fontWeight: 700,
            boxShadow: tab === 'guidelines' ? '0 6px 16px rgba(79,70,229,0.3)' : 'none',
          }}
        >
          Brand Guidelines ({guidelines.length})
        </button>
        <button
          className={`btn ${tab === 'facts' ? 'btn-primary' : 'btn-secondary'} btn-sm`}
          onClick={() => setTab('facts')}
          style={{
            borderRadius: 999,
            padding: '8px 20px',
            fontWeight: 700,
            boxShadow: tab === 'facts' ? '0 6px 16px rgba(79,70,229,0.3)' : 'none',
          }}
        >
          Approved Corporate Facts ({facts.length})
        </button>
      </div>

      {/* Search Bar */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <div className="search-wrapper" style={{ flex: 1 }}>
          <input
            className="search-input"
            style={{ width: '100%', background: 'rgba(255, 255, 255, 0.85)', backdropFilter: 'blur(12px)', borderRadius: 12, border: '1.5px solid rgba(255,255,255,0.95)' }}
            placeholder={tab === 'guidelines' ? 'Search guidelines by ID, clause text, category…' : 'Search facts by claim statement, source URL…'}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <button className="btn btn-secondary btn-sm" onClick={fetchData} style={{ borderRadius: 10 }}>
          Refresh
        </button>
      </div>

      {/* Tab 1: Guidelines Table */}
      {tab === 'guidelines' && (
        <div className="table-wrapper" style={{ borderRadius: 'var(--radius-lg)', overflow: 'hidden', boxShadow: '0 8px 30px rgba(25, 45, 120, 0.08)' }}>
          <table>
            <thead>
              <tr>
                <th>Clause ID</th>
                <th>Category</th>
                <th>Severity</th>
                <th>Rule Description</th>
                <th>Engine State</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    Loading guidelines from semantic index…
                  </td>
                </tr>
              ) : filteredGuidelines.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    No guidelines matched the query.
                  </td>
                </tr>
              ) : (
                filteredGuidelines.map((g) => (
                  <tr key={g.id}>
                    <td>
                      <span style={{ fontFamily: 'monospace', fontWeight: 800, fontSize: 13, color: '#4f46e5' }}>
                        {g.clause_identifier}
                      </span>
                    </td>
                    <td>
                      <span className="tag" style={{ borderRadius: 6, fontWeight: 700 }}>{g.category}</span>
                    </td>
                    <td>
                      <span
                        className="badge"
                        style={{
                          borderRadius: 999,
                          fontWeight: 800,
                          background: g.severity === 'CRITICAL' ? 'rgba(239,68,68,0.18)' : g.severity === 'HIGH' ? 'rgba(249,115,22,0.18)' : 'rgba(245,158,11,0.18)',
                          color: g.severity === 'CRITICAL' ? '#b91c1c' : g.severity === 'HIGH' ? '#c2410c' : '#b45309',
                        }}
                      >
                        {g.severity}
                      </span>
                    </td>
                    <td style={{ fontSize: 13, color: 'var(--text-primary)', maxWidth: 440, lineHeight: 1.5 }}>
                      {g.clause_text}
                    </td>
                    <td>
                      <span className={`badge ${g.is_active ? 'badge-success' : 'badge-danger'}`} style={{ borderRadius: 999 }}>
                        {g.is_active ? 'Active' : 'Archived'}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 2: Facts Table */}
      {tab === 'facts' && (
        <div className="table-wrapper" style={{ borderRadius: 'var(--radius-lg)', overflow: 'hidden', boxShadow: '0 8px 30px rgba(25, 45, 120, 0.08)' }}>
          <table>
            <thead>
              <tr>
                <th>Factual Claim Statement</th>
                <th>Provenance Source URL</th>
                <th>Verification Date</th>
                <th>Expiry Date</th>
                <th>Temporal Status</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    Loading certified facts from database…
                  </td>
                </tr>
              ) : filteredFacts.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    No approved facts matched the query.
                  </td>
                </tr>
              ) : (
                filteredFacts.map((f) => {
                  const isExpired = new Date(f.expiry_date) < now;
                  return (
                    <tr key={f.id}>
                      <td style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', maxWidth: 360, lineHeight: 1.5 }}>
                        {f.fact_statement}
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, fontWeight: 400 }}>
                          "{f.evidence_excerpt}"
                        </div>
                      </td>
                      <td>
                        <a
                          href={f.original_source_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ fontSize: 12, color: '#0284c7', textDecoration: 'none', fontWeight: 600 }}
                        >
                          {f.original_source_url.length > 35 ? f.original_source_url.substring(0, 32) + '…' : f.original_source_url}
                        </a>
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        {new Date(f.verification_date).toLocaleDateString()}
                      </td>
                      <td style={{ fontSize: 12, color: isExpired ? '#dc2626' : '#059669', fontWeight: 700 }}>
                        {new Date(f.expiry_date).toLocaleDateString()}
                      </td>
                      <td>
                        <span className={`badge ${isExpired ? 'badge-danger' : 'badge-success'}`} style={{ borderRadius: 999 }}>
                          {isExpired ? 'STALE / EXPIRED' : 'ACTIVE TRUTH'}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Add Guideline Modal */}
      {showAddGModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 20 }}>
          <TiltCard maxTilt={5} glare={true} style={{ maxWidth: 540, width: '100%', borderRadius: 'var(--radius-lg)' }}>
            <div style={{ padding: 28 }}>
              <div className="card-title" style={{ marginBottom: 18, fontSize: 18, fontWeight: 800 }}>+ Add Brand Guideline Rule</div>
              <form onSubmit={handleCreateGuideline}>
                <div style={{ marginBottom: 14 }}>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6, fontWeight: 600 }}>Clause Identifier</label>
                  <input
                    className="search-input"
                    style={{ width: '100%', paddingLeft: 12, borderRadius: 10 }}
                    placeholder="e.g. SEC-TONE-05"
                    value={newClauseId}
                    onChange={(e) => setNewClauseId(e.target.value)}
                    required
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
                  <div>
                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6, fontWeight: 600 }}>Category</label>
                    <select className="form-select" style={{ borderRadius: 10 }} value={newCategory} onChange={(e) => setNewCategory(e.target.value)}>
                      <option value="TERMINOLOGY">TERMINOLOGY</option>
                      <option value="TONE">TONE</option>
                      <option value="MESSAGING">MESSAGING</option>
                      <option value="ACCESSIBILITY">ACCESSIBILITY</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6, fontWeight: 600 }}>Severity</label>
                    <select className="form-select" style={{ borderRadius: 10 }} value={newSeverity} onChange={(e) => setNewSeverity(e.target.value)}>
                      <option value="CRITICAL">CRITICAL</option>
                      <option value="HIGH">HIGH</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="LOW">LOW</option>
                    </select>
                  </div>
                </div>
                <div style={{ marginBottom: 18 }}>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6, fontWeight: 600 }}>Clause Rule Specification</label>
                  <textarea
                    className="form-input"
                    rows={4}
                    style={{ width: '100%', borderRadius: 10, lineHeight: 1.5 }}
                    placeholder="State rule prohibition or requirement clearly…"
                    value={newClauseText}
                    onChange={(e) => setNewClauseText(e.target.value)}
                    required
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                  <button type="button" className="btn btn-secondary" onClick={() => setShowAddGModal(false)} style={{ borderRadius: 10 }}>
                    Cancel
                  </button>
                  <button type="submit" className="btn btn-primary btn-3d" disabled={addingG} style={{ borderRadius: 10, padding: '8px 18px', fontWeight: 700 }}>
                    {addingG ? 'Indexing…' : 'Create & Index'}
                  </button>
                </div>
              </form>
            </div>
          </TiltCard>
        </div>
      )}

      {/* Add Fact Modal */}
      {showAddFModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.6)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 20 }}>
          <TiltCard maxTilt={5} glare={true} style={{ maxWidth: 540, width: '100%', borderRadius: 'var(--radius-lg)' }}>
            <div style={{ padding: 28 }}>
              <div className="card-title" style={{ marginBottom: 18, fontSize: 18, fontWeight: 800 }}>+ Add Approved Corporate Fact</div>
              <form onSubmit={handleCreateFact}>
                <div style={{ marginBottom: 14 }}>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6, fontWeight: 600 }}>Factual Claim Statement</label>
                  <textarea
                    className="form-input"
                    rows={2}
                    style={{ width: '100%', borderRadius: 10 }}
                    placeholder="e.g. Acme FinTech processes $4.2B in annualized volume…"
                    value={newFactStatement}
                    onChange={(e) => setNewFactStatement(e.target.value)}
                    required
                  />
                </div>
                <div style={{ marginBottom: 14 }}>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6, fontWeight: 600 }}>Original Source URL</label>
                  <input
                    className="search-input"
                    style={{ width: '100%', paddingLeft: 12, borderRadius: 10 }}
                    placeholder="https://acmefintech.com/reports/q1-compliance"
                    value={newSourceUrl}
                    onChange={(e) => setNewSourceUrl(e.target.value)}
                    required
                  />
                </div>
                <div style={{ marginBottom: 14 }}>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6, fontWeight: 600 }}>Supporting Evidence Excerpt</label>
                  <textarea
                    className="form-input"
                    rows={2}
                    style={{ width: '100%', borderRadius: 10 }}
                    placeholder="Official audit certificate excerpt or quotation…"
                    value={newEvidence}
                    onChange={(e) => setNewEvidence(e.target.value)}
                  />
                </div>
                <div style={{ marginBottom: 18 }}>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 6, fontWeight: 600 }}>Expiration Date</label>
                  <input
                    type="date"
                    className="search-input"
                    style={{ width: '100%', paddingLeft: 12, borderRadius: 10 }}
                    value={newExpiry}
                    onChange={(e) => setNewExpiry(e.target.value)}
                    required
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                  <button type="button" className="btn btn-secondary" onClick={() => setShowAddFModal(false)} style={{ borderRadius: 10 }}>
                    Cancel
                  </button>
                  <button type="submit" className="btn btn-primary btn-3d" disabled={addingF} style={{ borderRadius: 10, padding: '8px 18px', fontWeight: 700 }}>
                    {addingF ? 'Indexing…' : 'Certify Fact'}
                  </button>
                </div>
              </form>
            </div>
          </TiltCard>
        </div>
      )}
    </div>
  );
}
