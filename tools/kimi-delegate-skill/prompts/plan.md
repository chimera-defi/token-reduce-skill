You are generating a strict delegation envelope.

Required output: JSON object with keys:
- goal: string
- task_class: one of [search, summarize, draft, review, implementation-lite]
- context_summary: string
- constraints: object
  - max_output_tokens: integer
  - timeout_seconds: integer
  - no_network: boolean
- acceptance: array of strings
- output_schema: object
  - format: one of [markdown, json, bullet-list]
  - required_sections: array of strings
- write_scope: array of path globs
- escalation_rules: array of strings

Rules:
- Keep context summary concise.
- Reject vague goals with missing acceptance criteria.
- Never include secrets.
