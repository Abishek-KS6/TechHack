import React from 'react';
import { useNavigate } from 'react-router-dom';

export default function LandingPage() {
  const navigate = useNavigate();

  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="ref-landing-wrapper">
      {/* ── 3D Geometric Floating Scene (exact match to reference screenshot) ── */}
      <div className="landing-geom-scene" aria-hidden="true">
        {/* Top-Right 3D Blue Cube */}
        <div className="landing-geom-cube">
          <svg width="150" height="150" viewBox="0 0 140 140" fill="none">
            <defs>
              <linearGradient id="lCubeTop" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#7da2ff" />
                <stop offset="100%" stopColor="#4f79f5" />
              </linearGradient>
              <linearGradient id="lCubeLeft" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#3b66e8" />
                <stop offset="100%" stopColor="#254bc4" />
              </linearGradient>
              <linearGradient id="lCubeRight" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#2950d6" />
                <stop offset="100%" stopColor="#1a359e" />
              </linearGradient>
              <filter id="lCubeShadow" x="-20%" y="-20%" width="150%" height="150%">
                <feDropShadow dx="10" dy="20" stdDeviation="16" floodColor="#1e327b" floodOpacity="0.35" />
              </filter>
            </defs>
            <g filter="url(#lCubeShadow)">
              <polygon points="70,18 122,46 70,74 18,46" fill="url(#lCubeTop)" />
              <polygon points="18,46 70,74 70,126 18,98" fill="url(#lCubeLeft)" />
              <polygon points="70,74 122,46 122,98 70,126" fill="url(#lCubeRight)" />
            </g>
          </svg>
        </div>

        {/* Top-Right 3D Jack / Star polyhedron */}
        <div className="landing-geom-jack-right">
          <svg width="90" height="90" viewBox="0 0 100 100" fill="none">
            <circle cx="50" cy="50" r="18" fill="#a4b4cf" />
            <circle cx="50" cy="18" r="14" fill="#cbd7eb" />
            <circle cx="50" cy="82" r="14" fill="#8898b8" />
            <circle cx="18" cy="50" r="14" fill="#b9c8e2" />
            <circle cx="82" cy="50" r="14" fill="#7587a8" />
            <circle cx="27" cy="27" r="12" fill="#d8e3f5" />
            <circle cx="73" cy="73" r="12" fill="#6a7c9d" />
          </svg>
        </div>

        {/* Middle-Left 3D Jack */}
        <div className="landing-geom-jack-left">
          <svg width="80" height="80" viewBox="0 0 100 100" fill="none">
            <circle cx="50" cy="50" r="18" fill="#a4b4cf" opacity="0.8" />
            <circle cx="50" cy="18" r="14" fill="#cbd7eb" opacity="0.8" />
            <circle cx="50" cy="82" r="14" fill="#8898b8" opacity="0.8" />
            <circle cx="18" cy="50" r="14" fill="#b9c8e2" opacity="0.8" />
            <circle cx="82" cy="50" r="14" fill="#7587a8" opacity="0.8" />
          </svg>
        </div>

        {/* Bottom-Left 3D Blue Torus / Donut */}
        <div className="landing-geom-torus">
          <svg width="170" height="170" viewBox="0 0 150 150" fill="none">
            <defs>
              <radialGradient id="lTorusGrad" cx="35%" cy="30%" r="75%">
                <stop offset="0%" stopColor="#608bff" />
                <stop offset="45%" stopColor="#305fee" />
                <stop offset="80%" stopColor="#1a40bc" />
                <stop offset="100%" stopColor="#0f267a" />
              </radialGradient>
              <filter id="lTorusShadow" x="-20%" y="-20%" width="150%" height="150%">
                <feDropShadow dx="-8" dy="18" stdDeviation="18" floodColor="#1a2d72" floodOpacity="0.4" />
              </filter>
            </defs>
            <g filter="url(#lTorusShadow)">
              <path
                d="M 75 18 C 108 18 134 42 134 75 C 134 108 108 132 75 132 C 42 132 16 108 16 75 C 16 42 42 18 75 18 Z M 75 48 C 60 48 48 60 48 75 C 48 90 60 102 75 102 C 90 102 102 90 102 75 C 102 60 90 48 75 48 Z"
                fill="url(#lTorusGrad)"
                transform="rotate(-26 75 75)"
              />
            </g>
          </svg>
        </div>

        {/* Depth of field floating blurred dark spheres */}
        <div className="landing-dark-sphere sphere-left" />
        <div className="landing-dark-sphere sphere-right-large" />
        <div className="landing-dark-sphere sphere-right-small" />

        {/* 4-point sparkle star bottom-right */}
        <div className="landing-sparkle">
          <svg width="36" height="36" viewBox="0 0 40 40" fill="none">
            <path d="M 20 0 Q 20 20 40 20 Q 20 20 20 40 Q 20 20 0 20 Q 20 20 20 0 Z" fill="#ffffff" opacity="0.9" />
          </svg>
        </div>
      </div>

      {/* ── Floating Frosted Glass Navbar Pill (exact match) ── */}
      <header className="landing-glass-nav-container">
        <nav className="landing-glass-nav" aria-label="Main Navigation">
          <div className="landing-logo" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <div className="ref-nav-icon" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, borderRadius: 6, background: '#4f46e5', color: '#fff', fontWeight: 800, fontSize: 13 }}>BS</div>
            <div>
              <div className="ref-nav-title">BrandShield AI</div>
              <div className="ref-nav-sub">CONTENT GOVERNANCE &amp; BRAND SAFETY</div>
            </div>
          </div>

          <div className="landing-glass-links">
            <button
              type="button"
              className="landing-glass-link"
              onClick={() => scrollToSection('features')}
            >
              Features
            </button>
            <button
              type="button"
              className="landing-glass-link"
              onClick={() => scrollToSection('how-it-works')}
            >
              How It Works
            </button>
            <button
              type="button"
              className="landing-glass-link"
              onClick={() => scrollToSection('governance')}
            >
              Governance
            </button>
            <button
              type="button"
              className="landing-glass-link"
              onClick={() => navigate('/login')}
            >
              Sign In
            </button>
            <button
              type="button"
              className="ref-purple-btn ref-purple-btn-sm"
              onClick={() => navigate('/login')}
            >
              Get Started →
            </button>
          </div>
        </nav>
      </header>

      {/* ── Hero Section (Refined, Focused & Uncluttered) ── */}
      <main className="ref-hero-container">
        <div className="ref-hero-content">
          <h1 className="ref-hero-h1">
            Protect Your Brand<br />
            Before You Publish.
          </h1>

          <p className="ref-hero-desc">
            BrandShield AI uses a 4-stage verification pipeline — Aho-Corasick
            terminology matching, temporal fact grounding, privacy-gated boundaries,
            and confidence-calibrated triage — to catch compliance violations before
            they reach your audience.
          </p>

          <div className="ref-hero-btn-row">
            <button
              type="button"
              className="ref-purple-btn ref-purple-btn-lg"
              onClick={() => navigate('/login')}
            >
              Get Started →
            </button>
            <button
              type="button"
              className="ref-dark-pill-btn ref-dark-btn-lg"
              onClick={() => scrollToSection('features')}
            >
              Explore Features
            </button>
          </div>
        </div>
      </main>

      {/* ── Features Section (Frosted Glass Theme) ── */}
      <section id="features" className="ref-landing-section">
        <div className="ref-section-inner">
          <div className="ref-section-badge">CORE CAPABILITIES</div>
          <h2 className="ref-section-h2">Essential Brand Protection</h2>
          <p className="ref-section-p">
            Engineered for organizations where non-compliant copy triggers severe legal liabilities.
          </p>

          <div className="ref-features-grid">
            {[
              {
                title: 'Evidence-Linked Findings',
                desc: 'Understand each issue with supporting evidence or a “Needs verification” status without hallucinated verdicts.',
              },
              {
                title: 'AI-Powered Content Verification',
                desc: 'Detect brand-rule violations, unsupported claims, and outdated facts across documents before publication.',
              },
              {
                title: 'Human-Controlled Approval',
                desc: 'Edit, review, approve, or request changes without automatically publishing content. Creators cannot self-approve.',
              },
              {
                title: 'Governance & Audit',
                desc: 'Track recurring issues, review history, and compliance trends with an immutable Merkle audit ledger in PostgreSQL.',
              },
            ].map((f) => (
              <div key={f.title} className="ref-feature-glass-card">
                <h3 className="ref-feature-title">{f.title}</h3>
                <p className="ref-feature-desc">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How It Works Section ── */}
      <section id="how-it-works" className="ref-landing-section">
        <div className="ref-section-inner">
          <div className="ref-section-badge">WORKFLOW</div>
          <h2 className="ref-section-h2">How BrandShield AI Works</h2>
          <p className="ref-section-p">
            A simple, reliable four-step process before any asset is cleared for publication.
          </p>

          <div className="ref-how-grid">
            {[
              {
                step: '01',
                title: 'Upload Document',
                desc: 'Drop your PDF, DOCX, or plain text. Magic-byte validation prevents spoofing, and AST maps every character offset.',
              },
              {
                step: '02',
                title: 'Analyze Content',
                desc: 'Four automated stages scan against brand guidelines, temporal fact grounding, and privacy-gated checks.',
              },
              {
                step: '03',
                title: 'Review & Correct',
                desc: 'Inspect flagged spans, review source citations, and accept suggestions or author revisions on the Merkle DAG.',
              },
              {
                step: '04',
                title: 'Approve Before Publishing',
                desc: 'Authorized Reviewers evaluate unified diffs and issue cryptographic clearance before publication.',
              },
            ].map((s) => (
              <div key={s.step} className="ref-how-glass-card">
                <div className="ref-how-step-tag">{s.step}</div>
                <h3 className="ref-how-title">{s.title}</h3>
                <p className="ref-how-desc">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Governance & Evidence-Linked Verification ── */}
      <section id="governance" className="ref-landing-section">
        <div className="ref-section-inner">
          <div className="ref-split-layout">
            <div className="ref-split-left">
              <div className="ref-section-badge">EVIDENCE-LINKED VERIFICATION</div>
              <h2 className="ref-section-h2" style={{ textAlign: 'left', marginBottom: 16 }}>
                Evidence Before Every Verdict
              </h2>
              <p className="ref-section-p" style={{ textAlign: 'left', margin: '0 0 24px 0' }}>
                BrandShield AI never marks an objective statement compliant without cross-referencing
                an unexpired ground-truth factual record.
              </p>

              <div className="ref-guarantee-list">
                {[
                  { label: 'High confidence (≥90%)', value: 'Flagged with cited ground truth link' },
                  { label: 'Low confidence (60–90%)', value: 'Routed directly to human reviewer queue' },
                  { label: 'Missing ground truth', value: 'Marked "Needs Verification" — unconfirmed without evidence' },
                  { label: 'Audit trail', value: 'Tamper-evident SHA-256 hash chained ledger' },
                ].map((item) => (
                  <div key={item.label} className="ref-guarantee-item">
                    <div className="ref-guarantee-dot" />
                    <div>
                      <div className="ref-guarantee-label">{item.label}</div>
                      <div className="ref-guarantee-val">{item.value}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="ref-split-right">
              <div className="ref-matrix-card">
                <div className="ref-matrix-title">Compliance Confidence Matrix (Sample Benchmark)</div>
                {[
                  { label: 'Approved & Grounded', pct: 68, color: '#059669' },
                  { label: 'Needs Human Review', pct: 22, color: '#d97706' },
                  { label: 'Needs Verification', pct: 7, color: '#4f46e5' },
                  { label: 'Critical Violation', pct: 3, color: '#dc2626' },
                ].map((bar) => (
                  <div key={bar.label} style={{ marginBottom: 14 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 5 }}>
                      <span style={{ color: '#1e293b', fontWeight: 600 }}>{bar.label}</span>
                      <span style={{ color: bar.color, fontWeight: 700 }}>{bar.pct}%</span>
                    </div>
                    <div style={{ height: 9, background: 'rgba(255,255,255,0.7)', borderRadius: 999, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${bar.pct}%`, background: bar.color, borderRadius: 999 }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Final Call to Action ── */}
      <section className="ref-landing-section ref-cta-wrap">
        <div className="ref-section-inner" style={{ textAlign: 'center' }}>
          <h2 className="ref-section-h2" style={{ fontSize: 38 }}>
            Verify Before You Publish.
          </h2>
          <p className="ref-section-p" style={{ maxWidth: 580, margin: '0 auto 28px' }}>
            Review content, resolve findings, and maintain a clear approval history with BrandShield AI.
          </p>
          <div style={{ display: 'flex', gap: 14, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="ref-purple-btn ref-purple-btn-lg"
              onClick={() => navigate('/login')}
            >
              Get Started →
            </button>
            <button
              type="button"
              className="ref-dark-pill-btn ref-dark-btn-lg"
              onClick={() => scrollToSection('features')}
            >
              Explore Features
            </button>
          </div>
          <div style={{ marginTop: 24, fontSize: 13, color: '#334155', fontWeight: 500 }}>
            SSO &amp; RBAC Active · Creator, Reviewer &amp; Administrator Access
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="ref-landing-footer">
        <div className="ref-footer-inner">
          <div className="landing-logo" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <div className="ref-nav-icon" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, borderRadius: 6, background: '#4f46e5', color: '#fff', fontWeight: 800, fontSize: 13 }}>BS</div>
            <div>
              <div className="ref-nav-title">BrandShield AI</div>
              <div className="ref-nav-sub">CONTENT GOVERNANCE &amp; BRAND SAFETY</div>
            </div>
          </div>
          <div style={{ color: '#334155', fontSize: 13, fontWeight: 500 }}>
            © 2026 BrandShield AI. All rights reserved. Brand Safety &amp; Audit Perimeter.
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <span style={{ color: '#475569', fontSize: 12, fontWeight: 600 }}>FTC Compliant</span>
            <span style={{ color: '#475569', fontSize: 12, fontWeight: 600 }}>GDPR Ready</span>
            <span style={{ color: '#475569', fontSize: 12, fontWeight: 600 }}>SOC2 Audit Trail</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
