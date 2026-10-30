import React from 'react';
import { Shield, CheckCircle2, Lock } from 'lucide-react';

interface ThreeDShieldBadgeProps {
  isValid?: boolean;
  totalBlocks?: number;
  blockCount?: number;
  subtitle?: string;
}

/**
 * ThreeDShieldBadge - Holographic 3D Cryptographic Verification Seal
 * Features 3D floating layers, glowing energy rings, and metallic specular highlights.
 */
export default function ThreeDShieldBadge({
  isValid = true,
  totalBlocks,
  blockCount,
  subtitle = 'SHA-256 Merkle Ledger',
}: ThreeDShieldBadgeProps) {
  const displayBlocks = blockCount ?? totalBlocks ?? 27;
  return (
    <div className="three-d-shield-container">
      <div className="three-d-shield-card">
        {/* Ambient Ring Glow */}
        <div className="shield-ambient-glow" />
        
        {/* Orbital 3D Rings */}
        <div className="shield-orbital-ring ring-1" />
        <div className="shield-orbital-ring ring-2" />

        {/* 3D Floating Core */}
        <div className="shield-core-box">
          <div className="shield-icon-wrapper">
            <Shield className="shield-svg" size={38} />
            <div className="shield-lock-icon">
              {isValid ? <CheckCircle2 size={16} /> : <Lock size={16} />}
            </div>
          </div>
        </div>

        {/* Metadata */}
        <div className="shield-meta">
          <div className="shield-status-pill">
            <span className="pulse-dot" />
            <span className="status-text">{isValid ? 'Chain Validated' : 'Verification Required'}</span>
          </div>
          <div className="shield-blocks-count">{displayBlocks} Blocks Chained</div>
          <div className="shield-subtitle">{subtitle}</div>
        </div>
      </div>
    </div>
  );
}
