"""
BrandShield AI - OpenAPI & Postman Contracts Exporter.
Automatically dumps docs/openapi.json and generates docs/BrandShield_AI.postman_collection.json
pre-configured with all endpoints, environment variables, and demo JWT workflows.
"""

import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import app

DOCS_DIR = REPO_ROOT / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def export_openapi():
    """Extracts and writes FastAPI OpenAPI schema to docs/openapi.json."""
    openapi_schema = app.openapi()
    target_path = DOCS_DIR / "openapi.json"
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
    print(f"  [OK] Exported OpenAPI specification: {target_path} ({target_path.stat().st_size} bytes)")
    return openapi_schema


def generate_postman_collection(openapi_schema: dict):
    """
    Transforms the application routes into a complete Postman v2.1.0 Collection
    with Bearer authentication, environment variables, and categorized folders.
    """
    collection = {
        "info": {
            "name": "BrandShield AI - Enterprise API Collection",
            "_postman_id": "7b1bb31a-f2e6-4e16-b01e-06d5366686db",
            "description": "Complete production API suite for BrandShield AI (FastAPI, Async SQLAlchemy 2.0, pgvector, Merkle audit ledger).",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {"key": "baseUrl", "value": "http://localhost:8000", "type": "string"},
            {"key": "creator_token", "value": "", "type": "string"},
            {"key": "reviewer_token", "value": "", "type": "string"},
            {"key": "admin_token", "value": "", "type": "string"},
            {"key": "demo_brand_profile_id", "value": "00000000-0000-0000-0000-000000000001", "type": "string"},
            {"key": "submission_id", "value": "", "type": "string"},
        ],
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{creator_token}}", "type": "string"}],
        },
        "item": [],
    }

    folders: dict[str, list[dict]] = {
        "1. Authentication & RBAC": [
            {
                "name": "Login (Creator) - Save Token",
                "request": {
                    "method": "POST",
                    "auth": {"type": "noauth"},
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/auth/token",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "auth", "token"],
                    },
                    "body": {
                        "mode": "urlencoded",
                        "urlencoded": [
                            {"key": "username", "value": "creator@acmefintech.com", "type": "text"},
                            {"key": "password", "value": "DemoSecure2026!", "type": "text"},
                        ],
                    },
                },
                "event": [
                    {
                        "listen": "test",
                        "script": {
                            "exec": [
                                "var jsonData = pm.response.json();",
                                "if (jsonData.access_token) {",
                                "    pm.environment.set('creator_token', jsonData.access_token);",
                                "}",
                            ],
                            "type": "text/javascript",
                        },
                    }
                ],
            },
            {
                "name": "Login (Reviewer) - Save Token",
                "request": {
                    "method": "POST",
                    "auth": {"type": "noauth"},
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/auth/token",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "auth", "token"],
                    },
                    "body": {
                        "mode": "urlencoded",
                        "urlencoded": [
                            {"key": "username", "value": "reviewer@acmefintech.com", "type": "text"},
                            {"key": "password", "value": "DemoSecure2026!", "type": "text"},
                        ],
                    },
                },
                "event": [
                    {
                        "listen": "test",
                        "script": {
                            "exec": [
                                "var jsonData = pm.response.json();",
                                "if (jsonData.access_token) {",
                                "    pm.environment.set('reviewer_token', jsonData.access_token);",
                                "}",
                            ],
                            "type": "text/javascript",
                        },
                    }
                ],
            },
            {
                "name": "Get Current Authenticated User",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/auth/me",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "auth", "me"],
                    },
                },
            },
        ],
        "2. Brand Profiles & Assets": [
            {
                "name": "List Workspace Brand Profiles",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/brands",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "brands"],
                    },
                },
            },
            {
                "name": "Get Specific Brand Profile",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/brands/{{demo_brand_profile_id}}",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "brands", "{{demo_brand_profile_id}}"],
                    },
                },
            },
            {
                "name": "List Brand Visual Assets",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/brands/{{demo_brand_profile_id}}/assets",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "brands", "{{demo_brand_profile_id}}", "assets"],
                    },
                },
            },
        ],
        "3. Document Ingestion & AST": [
            {
                "name": "Submit Raw Text Document",
                "request": {
                    "method": "POST",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/submissions/text",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "submissions", "text"],
                    },
                    "body": {
                        "mode": "raw",
                        "raw": json.dumps(
                            {
                                "title": "Acme Q3 Press Release Passage",
                                "brand_profile_id": "{{demo_brand_profile_id}}",
                                "content": "Acme FinTech provides a 100% risk-free settlement with a guaranteed monopoly.",
                                "document_type": "TEXT",
                            },
                            indent=2,
                        ),
                    },
                },
            },
            {
                "name": "Upload Binary Document (PDF/DOCX)",
                "request": {
                    "method": "POST",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/submissions/upload",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "submissions", "upload"],
                    },
                    "body": {
                        "mode": "formdata",
                        "formdata": [
                            {"key": "title", "value": "Corporate Press Release Upload", "type": "text"},
                            {"key": "brand_profile_id", "value": "{{demo_brand_profile_id}}", "type": "text"},
                            {"key": "file", "type": "file", "src": "demo_artifacts/acme_q3_press_release.pdf"},
                        ],
                    },
                },
            },
            {
                "name": "Get Submission by ID",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/submissions/{{submission_id}}",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "submissions", "{{submission_id}}"],
                    },
                },
            },
            {
                "name": "List Revision DAG History",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/submissions/{{submission_id}}/revisions",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "submissions", "{{submission_id}}", "revisions"],
                    },
                },
            },
        ],
        "4. Analysis Pipeline & Real-Time SSE": [
            {
                "name": "Trigger Analysis on Submission",
                "request": {
                    "method": "POST",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/analysis/submissions/{{submission_id}}/run",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "analysis", "submissions", "{{submission_id}}", "run"],
                    },
                },
            },
            {
                "name": "Real-Time SSE Analysis Stream",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/submissions/{{submission_id}}/analyze/stream?token={{creator_token}}",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "submissions", "{{submission_id}}", "analyze", "stream"],
                        "query": [{"key": "token", "value": "{{creator_token}}"}],
                    },
                },
            },
        ],
        "5. Workflow & Human Review Sign-Off": [
            {
                "name": "Submit for Human Review",
                "request": {
                    "method": "POST",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/workflow/{{submission_id}}/submit-for-review",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "workflow", "{{submission_id}}", "submit-for-review"],
                    },
                },
            },
            {
                "name": "Execute Review Decision (Reviewer Only)",
                "request": {
                    "method": "POST",
                    "auth": {
                        "type": "bearer",
                        "bearer": [{"key": "token", "value": "{{reviewer_token}}", "type": "string"}],
                    },
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/workflow/{{submission_id}}/review",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "workflow", "{{submission_id}}", "review"],
                    },
                    "body": {
                        "mode": "raw",
                        "raw": json.dumps(
                            {
                                "decision": "APPROVED",
                                "comments": "All terminology and claim verifications satisfied.",
                            },
                            indent=2,
                        ),
                    },
                },
            },
            {
                "name": "Get Revision Lineage Token Diff",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/workflow/{{submission_id}}/revisions/diff?from_revision=1&to_revision=2",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "workflow", "{{submission_id}}", "revisions", "diff"],
                        "query": [
                            {"key": "from_revision", "value": "1"},
                            {"key": "to_revision", "value": "2"},
                        ],
                    },
                },
            },
        ],
        "6. Governance, Audit & Evaluation": [
            {
                "name": "Get Governance Report (Recharts Formatted)",
                "request": {
                    "method": "GET",
                    "auth": {
                        "type": "bearer",
                        "bearer": [{"key": "token", "value": "{{reviewer_token}}", "type": "string"}],
                    },
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/governance/reports",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "governance", "reports"],
                    },
                },
            },
            {
                "name": "Get Traceability Grounding Metrics",
                "request": {
                    "method": "GET",
                    "auth": {
                        "type": "bearer",
                        "bearer": [{"key": "token", "value": "{{reviewer_token}}", "type": "string"}],
                    },
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/governance/traceability-metrics",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "governance", "traceability-metrics"],
                    },
                },
            },
            {
                "name": "Execute Labelled Benchmark Evaluation",
                "request": {
                    "method": "POST",
                    "auth": {
                        "type": "bearer",
                        "bearer": [{"key": "token", "value": "{{reviewer_token}}", "type": "string"}],
                    },
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/governance/evaluate-testset",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "governance", "evaluate-testset"],
                    },
                },
            },
            {
                "name": "Verify SHA-256 Merkle Audit Chain (Admin Only)",
                "request": {
                    "method": "POST",
                    "auth": {
                        "type": "bearer",
                        "bearer": [{"key": "token", "value": "{{admin_token}}", "type": "string"}],
                    },
                    "url": {
                        "raw": "{{baseUrl}}/api/v1/governance/audit-verify",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "v1", "governance", "audit-verify"],
                    },
                },
            },
        ],
    }

    for folder_name, items in folders.items():
        collection["item"].append({"name": folder_name, "item": items})

    target_path = DOCS_DIR / "BrandShield_AI.postman_collection.json"
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)
    print(f"  [OK] Exported Postman collection: {target_path} ({target_path.stat().st_size} bytes)")


def main():
    print("Exporting API specifications and contracts to docs/...")
    openapi = export_openapi()
    generate_postman_collection(openapi)
    print("API contracts export completed successfully.")


if __name__ == "__main__":
    main()
