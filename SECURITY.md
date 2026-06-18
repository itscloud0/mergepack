# Security

## Supported Versions

Only the latest release is supported during early v0.x development.

## Reporting A Vulnerability

Open a GitHub security advisory or a private report if the repository is public. Do not include secrets in public issues.

## Scope

`mergepack` reads git diffs and writes review artifacts. It does not call external LLM APIs and does not post PR comments by default.

## Sensitive Diffs

Do not run `mergepack` on diffs that contain secrets, private keys, credentials, or private customer data. v0.1 can flag some sensitive-looking text, but it is not a secret scanner and does not guarantee redaction.
