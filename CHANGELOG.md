## [1.7.1](https://github.com/izzzzzi/izTeamSlots/compare/v1.7.0...v1.7.1) (2026-04-13)


### Bug Fixes

* **codex-switcher:** eliminate redundant _load_accounts calls in pick_first_ready ([1024e95](https://github.com/izzzzzi/izTeamSlots/commit/1024e9582137aeaaea43484c94002455160ed37d))
* deduplicate _decode_jwt_payload — single canonical implementation in codex_switcher ([5e579fe](https://github.com/izzzzzi/izTeamSlots/commit/5e579fe44caccf381d47d43484c56b4242589f87))
* **jobs:** move thread assignment inside lock to prevent race condition ([40a3be2](https://github.com/izzzzzi/izTeamSlots/commit/40a3be2ce0937ae6eeef72c508c820d5de2d1029))
* **logger:** use UTC timestamps consistent with rest of codebase ([302dfa1](https://github.com/izzzzzi/izTeamSlots/commit/302dfa1c2c5348fcab11c5606c5eb916ff0b5d26))
* remove redundant Mailbox creation in relogin_worker_email ([883af9b](https://github.com/izzzzzi/izTeamSlots/commit/883af9bd7650c887056885514329b38d6bd5acab))
* **security:** set chmod 0600 on meta.json and index.json files ([08c27af](https://github.com/izzzzzi/izTeamSlots/commit/08c27af9b330fae9f9a6316fd0fc7c6d38813506))
* **security:** strengthen API key masking — show at most 4 chars for long keys ([545ac15](https://github.com/izzzzzi/izTeamSlots/commit/545ac15c4505fa94aff59ef5f1ede2b11a8819c2))
* **workspace-api:** add pagination to get_members and get_pending_invites ([48229d2](https://github.com/izzzzzi/izTeamSlots/commit/48229d209a20593be9693df18f504dba9ee18ddc))

# [1.7.0](https://github.com/izzzzzi/izTeamSlots/compare/v1.6.1...v1.7.0) (2026-03-07)


### Bug Fixes

* remove unused variable to satisfy ruff F841 ([e5cfb77](https://github.com/izzzzzi/izTeamSlots/commit/e5cfb773e4449037aa96f7f940c22cd7eb78ecdc))


### Features

* add Codex account switcher with auto-rotation ([70c8953](https://github.com/izzzzzi/izTeamSlots/commit/70c8953a6cde92127a17a5ea220bd8476bbc3447))

## [1.6.1](https://github.com/izzzzzi/izTeamSlots/compare/v1.6.0...v1.6.1) (2026-03-07)


### Bug Fixes

* **ci:** install python deps before unit tests ([5c57d2a](https://github.com/izzzzzi/izTeamSlots/commit/5c57d2a5c9f22ed667d9cbdedacb69c465d136ba))

# [1.6.0](https://github.com/izzzzzi/izTeamSlots/compare/v1.5.5...v1.6.0) (2026-03-06)


### Features

* **auth:** disable automatic admin login ([930313f](https://github.com/izzzzzi/izTeamSlots/commit/930313f6ef2f06674cc9da6e8d45061dc8c89a93))

## [1.5.5](https://github.com/izzzzzi/izTeamSlots/compare/v1.5.4...v1.5.5) (2026-03-06)


### Bug Fixes

* **auth:** stabilize manual flows and tab focus ([1e909c2](https://github.com/izzzzzi/izTeamSlots/commit/1e909c220c3bf4120c5367e7e313632cc903a024))

## [1.5.4](https://github.com/izzzzzi/izTeamSlots/compare/v1.5.3...v1.5.4) (2026-03-06)


### Bug Fixes

* Windows compatibility — version check, wmic removal, CI matrix, venv resolution ([342b515](https://github.com/izzzzzi/izTeamSlots/commit/342b515e86ac7e674fed6c25c6dece20eb40b0ea))

## [1.5.3](https://github.com/izzzzzi/izTeamSlots/compare/v1.5.2...v1.5.3) (2026-03-06)


### Bug Fixes

* infrastructure hardening — atomic writes, DATA_ROOT, emergency exit, virtual scroll ([683dfd6](https://github.com/izzzzzi/izTeamSlots/commit/683dfd6670b0d4431b639331f2bc205f2fd8348a))

## [1.5.2](https://github.com/izzzzzi/izTeamSlots/compare/v1.5.1...v1.5.2) (2026-03-06)


### Bug Fixes

* security and thread-safety improvements from code review ([6356bfd](https://github.com/izzzzzi/izTeamSlots/commit/6356bfd9eded9379fe1424b20f954cec8e847c8b))

## [1.5.1](https://github.com/izzzzzi/izTeamSlots/compare/v1.5.0...v1.5.1) (2026-03-06)


### Bug Fixes

* use self.password_prefix in boomlify generate() instead of hardcoded string ([de0098a](https://github.com/izzzzzi/izTeamSlots/commit/de0098ad620ee3010c359155b726f097b15fb13f))

# [1.5.0](https://github.com/izzzzzi/izTeamSlots/compare/v1.4.0...v1.5.0) (2026-03-06)


### Features

* add password_prefix to trickads, use self.password_prefix in boomlify ([f1bfe71](https://github.com/izzzzzi/izTeamSlots/commit/f1bfe71eb7690602894ec5db4878c3115f122a07))

# [1.4.0](https://github.com/izzzzzi/izTeamSlots/compare/v1.3.3...v1.4.0) (2026-03-06)


### Features

* auto-discovery for mail providers — no manual registration needed ([ca54650](https://github.com/izzzzzi/izTeamSlots/commit/ca54650a42696b714c79cf328da5d58b5e2d1f60))

## [1.3.3](https://github.com/izzzzzi/izTeamSlots/compare/v1.3.2...v1.3.3) (2026-03-06)


### Bug Fixes

* quick start recommends configuring mail API key first ([c852b9d](https://github.com/izzzzzi/izTeamSlots/commit/c852b9d63d9e5867b897791e8fd11e712e1a515f))
* remove extra leading spaces from hero logo ([ddb43bb](https://github.com/izzzzzi/izTeamSlots/commit/ddb43bbc6ba0075736ac7acba433032b45dbfc37))

## [1.3.2](https://github.com/izzzzzi/izTeamSlots/compare/v1.3.1...v1.3.2) (2026-03-06)


### Bug Fixes

* force UTF-8 encoding for Python subprocess on Windows ([a31f376](https://github.com/izzzzzi/izTeamSlots/commit/a31f3764a9487a21718e93bddc22f9831179eed4))

## [1.3.1](https://github.com/izzzzzi/izTeamSlots/compare/v1.3.0...v1.3.1) (2026-03-06)


### Bug Fixes

* settings menu empty — prevent refreshState from overwriting loaded settings ([ce300c8](https://github.com/izzzzzi/izTeamSlots/commit/ce300c86e3be36048685c90f20abcec27c790284))

# [1.3.0](https://github.com/izzzzzi/izTeamSlots/compare/v1.2.0...v1.3.0) (2026-03-06)


### Features

* add Settings menu for API keys and mail providers ([e026db7](https://github.com/izzzzzi/izTeamSlots/commit/e026db7dd01db0544ad7993dfb6ab020490f2ae8))

# [1.2.0](https://github.com/izzzzzi/izTeamSlots/compare/v1.1.6...v1.2.0) (2026-03-06)


### Features

* load config from ~/.izteamslots/.env, update README install docs ([99ca787](https://github.com/izzzzzi/izTeamSlots/commit/99ca787207d65cfde29a9b0bd173dc870ca59ee6))

## [1.1.6](https://github.com/izzzzzi/izTeamSlots/compare/v1.1.5...v1.1.6) (2026-03-06)


### Bug Fixes

* add python-dotenv to requirements.txt (missing dependency) ([697d104](https://github.com/izzzzzi/izTeamSlots/commit/697d104a216ab75a66bd6e6f0ba4921f1bc1704e))

## [1.1.5](https://github.com/izzzzzi/izTeamSlots/compare/v1.1.4...v1.1.5) (2026-03-06)


### Bug Fixes

* use shell mode on Windows for spawn/exec (backend + bun launch) ([3dbc103](https://github.com/izzzzzi/izTeamSlots/commit/3dbc103b47268bd9260dcefe36cb4a5db668e243))

## [1.1.4](https://github.com/izzzzzi/izTeamSlots/compare/v1.1.3...v1.1.4) (2026-03-06)


### Bug Fixes

* use Node.js bin entry instead of .sh (fixes Windows npm bin) ([98f7336](https://github.com/izzzzzi/izTeamSlots/commit/98f7336a4706e84174fc90be8d628278f690e0d0))

## [1.1.3](https://github.com/izzzzzi/izTeamSlots/compare/v1.1.2...v1.1.3) (2026-03-06)


### Bug Fixes

* Windows compatibility — cross-platform process kill, clipboard, paths, setup ([96a1dc4](https://github.com/izzzzzi/izTeamSlots/commit/96a1dc4e70221c4546254447b8c5bbfe21a37f6b))

## [1.1.2](https://github.com/izzzzzi/izTeamSlots/compare/v1.1.1...v1.1.2) (2026-03-06)


### Bug Fixes

* use venv instead of --system for Python deps (fixes Windows/WSL permissions) ([232f174](https://github.com/izzzzzi/izTeamSlots/commit/232f174730402bac38d3b59eb7527702825b6df7))

## [1.1.1](https://github.com/izzzzzi/izTeamSlots/compare/v1.1.0...v1.1.1) (2026-03-06)


### Bug Fixes

* install semantic-release plugins before running release ([271cb07](https://github.com/izzzzzi/izTeamSlots/commit/271cb077b8cedaca300bdb001e0454d6ed43bcea))
* remove registry-url to avoid .npmrc conflict with semantic-release ([53a7839](https://github.com/izzzzzi/izTeamSlots/commit/53a783956e3073ad874e52f8378b0b9db4995ddd))
