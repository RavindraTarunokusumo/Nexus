# Patterns

Record repo-specific implementation patterns here as they emerge. The current design constraints come from [docs/specs/README.md](specs/README.md).

## Initial Patterns

- Keep domain-specific behavior in domain packs.
- Keep the LLM gateway reusable and logged.
- Validate structured model outputs before persistence.
- Preserve source provenance on every derived object.
- Prefer deterministic logic and local models before expensive model calls.
- Keep MVP scope focused on Source, Document, Span, Claim, Brief, and Agent Run layers.
