import React from 'react';
import { GitBranch, GitCommit, ArrowRight, ShieldCheck, CheckCircle2, AlertTriangle, FileText } from 'lucide-react';

export interface RevisionNode {
  revision_number: number;
  sha256_content_hash: string;
  created_at: string;
  created_by_name?: string;
  is_tip?: boolean;
  findings_count?: number;
  approved?: boolean;
}

interface ThreeDRevisionDagProps {
  revisions: RevisionNode[];
  activeRevision: number;
  onSelectRevision?: (revNumber: number) => void;
}

/**
 * ThreeDRevisionDag - Isometric 3D Document Revision Lineage Visualizer
 * Displays the immutable Git-like revision history as floating 3D nodes
 * with glowing connection beams and status indicators.
 */
export default function ThreeDRevisionDag({
  revisions,
  activeRevision,
  onSelectRevision,
}: ThreeDRevisionDagProps) {
  return (
    <div className="three-d-dag-container">
      <div className="dag-header">
        <div className="dag-title">
          <GitBranch size={16} className="text-indigo-400" />
          <span>Immutable Revision Lineage (DAG)</span>
        </div>
        <div className="dag-badge">
          <ShieldCheck size={13} />
          <span>SHA-256 Tamper-Evident</span>
        </div>
      </div>

      <div className="dag-track-isometric">
        {revisions.map((rev, idx) => {
          const isActive = rev.revision_number === activeRevision;
          const isLatest = idx === revisions.length - 1;
          const shortHash = rev.sha256_content_hash ? `${rev.sha256_content_hash.slice(0, 8)}…` : 'genesis';

          return (
            <React.Fragment key={rev.revision_number}>
              <div
                className={`dag-node-3d ${isActive ? 'active' : ''} ${rev.approved ? 'approved' : ''}`}
                onClick={() => onSelectRevision && onSelectRevision(rev.revision_number)}
                title={`Click to inspect Revision v${rev.revision_number}`}
              >
                <div className="node-3d-base">
                  <div className="node-3d-cap">
                    <GitCommit size={15} />
                    <span className="node-rev-label">v{rev.revision_number}</span>
                  </div>
                </div>

                <div className="node-info-card">
                  <div className="node-header-row">
                    <span className="node-v-tag">Version {rev.revision_number}</span>
                    {rev.approved ? (
                      <span className="node-status-approved">
                        <CheckCircle2 size={12} /> Approved
                      </span>
                    ) : (rev.findings_count && rev.findings_count > 0) ? (
                      <span className="node-status-flagged">
                        <AlertTriangle size={12} /> {rev.findings_count} Flags
                      </span>
                    ) : (
                      <span className="node-status-clean">Clean</span>
                    )}
                  </div>
                  <div className="node-hash-code">
                    <code>{shortHash}</code>
                  </div>
                  {rev.created_by_name && (
                    <div className="node-author">by {rev.created_by_name}</div>
                  )}
                </div>
              </div>

              {!isLatest && (
                <div className="dag-connector-beam">
                  <div className="beam-line" />
                  <div className="beam-pulse" />
                  <ArrowRight size={14} className="beam-arrow" />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

