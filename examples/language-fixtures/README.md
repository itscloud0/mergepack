# Language Fixtures

These fixtures exercise non-Python PR packets:

- `go-pr.diff` with `go-repo/` should suggest `go test ./...`.
- `rust-pr.diff` with `rust-repo/` should suggest `cargo test` and `cargo build`.
- `node-pr.diff` with `node-repo/` should suggest the package `test`, `lint`, `typecheck`, and `build` scripts through npm commands.
- `gradle-pr.diff` with `gradle-repo/` should suggest the root Gradle test and a module-scoped `:api:test` command.

The expected packet fields used by regression tests are in `expected-packets.json`.
