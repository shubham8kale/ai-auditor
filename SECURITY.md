# Security

AI Auditor is a personal project, with an authenticated hosted demonstration using
fictional examples. It is not a public document-upload service. Do not put real
client evidence, credentials, or local analysis into this repository or public issues.

## Access and data boundaries

- The API validates bearer tokens with Supabase and checks engagement ownership
  on document, source-file, revision, correction, chat, and export routes.
- Supabase app tables use row-level security, with direct table grants revoked
  from anonymous and authenticated public API roles. Source storage is private.
- Upload links are time-limited bearer capabilities. They allow request-list
  access and uploads, not source downloads or access to workpapers.
- Private API responses use `Cache-Control: no-store`. Browser responses carry
  a content-security policy, framing restrictions, and MIME-sniffing protection.
- Only intended public configuration and the publishable auth key reach the
  browser. Database, storage-admin, and model credentials remain server-side.
- The production container runs as a non-root user. Local auth bypass is forbidden
  in production. Original evidence and review history are separate from model output.

## Security review

The review covered repository files and Git objects, pinned dependencies, Python
static analysis, API ownership tests, and read-only live access/storage checks.
Administrative cleanup retired the former shared access account and its upload
links. Remaining hosted data was checked to contain only fictional engagements
and their 22 original files, with no orphaned storage objects.

| Check | Result |
| --- | --- |
| Tracked-file and configured-secret scan | No credentials or real-client names detected in the public source tree |
| Python runtime dependency audit | No known vulnerabilities reported by pip-audit |
| Frontend lockfile audit | No known vulnerabilities reported by npm audit |
| Python static security analysis | Bandit reported no findings in application code |
| Backend regression suite | 62 tests passed; Ruff passed |
| Frontend | TypeScript checking and Vite production build passed |
| Anonymous workspace and identity requests | Rejected with HTTP 401 |
| Database and storage | Seven app tables have RLS; no public-role table grants; evidence bucket is private |
| Retired account | Banned, password replaced, sessions and refresh tokens revoked, no engagement ownership |
| Live hardening deployment | Verified after `dd5242e`: homepage and database health pass; CSP/HSTS/nosniff headers present; protected paths return 404; anonymous API and portal access rejected; untrusted CORS origin denied |

The review found that a header-only request-size check did not bound chunked or
understated request bodies before multipart parsing. Requests are now bounded by
the bytes actually received, with malformed lengths rejected. Workbook parsing
now explicitly depends on `defusedxml` to reject XML entity expansion. Regression
tests cover these paths, and protected-path requests return 404 rather than the
single-page application shell. Deployment verification is recorded separately
from local test results; a passing local test does not prove a deployment updated.

## Limits

- This is a targeted review, not an independent penetration test or a guarantee
  that no vulnerability exists. Dependency databases only cover known reports.
- One process owns the job runner and model pacing. There is no distributed rate
  limiter or isolated document-processing sandbox. Keep access restricted; do not
  enable anonymous signup or expose this as an unrestricted upload endpoint.
- Body, file, workbook, page, queue, and document limits reduce resource abuse,
  but concurrent uploads and complex documents can still consume resources.
- Revoking access does not remove files somebody previously downloaded. Cloud
  backups and provider retention are separate from the active application tables.
- Public Git hosting may retain old commit views after a history rewrite. A clean
  branch does not establish removal of previously hosted copies.

If reporting a vulnerability, omit credentials, document contents, and personal
data from any public report. Contact the repository owner privately for sensitive
details; do not probe accounts or data you are not authorized to access.
