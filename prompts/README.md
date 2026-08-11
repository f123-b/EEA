# Prompt Registry

Prompt definitions are versioned domain records persisted through the PromptRepository port.
Templates may contain engineering context and JSON input placeholders, but never credentials.
The application layer verifies the registered output JSON Schema before every provider call.
