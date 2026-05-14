# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in LegalDev, **do not open a public GitHub issue**. Report it privately instead:

- **Email**: gustavintavo1202@gmail.com
- **Subject**: `[SECURITY] LegalDev — <short description>`

Include a description of the issue and its potential impact, steps to reproduce, and any proof-of-concept payload if applicable. You will receive a response within **7 days**. Confirmed issues will be patched as soon as possible.

## Scope

This project processes free-text user input and passes it to an LLM. Relevant attack surface:

- **Prompt injection** — malicious content in `descripcion_breve` or other free-text fields attempting to override the system prompt or hijack the LLM response
- **Sensitive data exposure** — inadvertent logging or leakage of user-submitted questionnaire data (names, emails, project descriptions)
- **Dependency vulnerabilities** — issues in FastAPI, LangChain, ChromaDB, or other dependencies that allow RCE or data exfiltration

## Out of Scope

- LLM output quality or legal accuracy (LegalDev is informative tooling, not legal advice)
- Rate limit bypass without demonstrated impact beyond the stated 10 req/min limit
- Issues requiring physical server access

## Disclosure Policy

Please allow reasonable time for a fix before public disclosure (coordinated/responsible disclosure).
