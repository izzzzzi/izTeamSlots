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
