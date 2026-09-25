# Changelog

## [0.0.5](https://github.com/ozanozbeker/epistole/compare/v0.0.4...v0.0.5) (2026-09-25)


### Features

* attach files and embed inline images ([8d43923](https://github.com/ozanozbeker/epistole/commit/8d4392375d11446d0e09b5830243d648dfd61c0e)), closes [#37](https://github.com/ozanozbeker/epistole/issues/37)
* build the RFC 5322 message ([6a853d1](https://github.com/ozanozbeker/epistole/commit/6a853d16f2b79ab16980568f4aac7e2af0a5785f)), closes [#41](https://github.com/ozanozbeker/epistole/issues/41)
* carry custom headers on a message ([0ac7440](https://github.com/ozanozbeker/epistole/commit/0ac7440031d2587cb2db231922dc6457687f2314)), closes [#40](https://github.com/ozanozbeker/epistole/issues/40)
* print a message with ConsoleBackend ([edee2fa](https://github.com/ozanozbeker/epistole/commit/edee2fa9a54998098f1a40e323ae92a4a3f21478)), closes [#42](https://github.com/ozanozbeker/epistole/issues/42)
* rewrite data: images into inline images ([ec9b755](https://github.com/ozanozbeker/epistole/commit/ec9b755afb438893c70ab831aefb30ee76d60973)), closes [#38](https://github.com/ozanozbeker/epistole/issues/38)
* send a Markdown message ([0c33fe8](https://github.com/ozanozbeker/epistole/commit/0c33fe8966e5dfc7f1722d568d21b776d6999e50)), closes [#39](https://github.com/ozanozbeker/epistole/issues/39)
* send an HTML message with derived plain text ([c140764](https://github.com/ozanozbeker/epistole/commit/c1407642301661597e3d8f4fa5d4df12cd47e2ed)), closes [#36](https://github.com/ozanozbeker/epistole/issues/36)
* send over Graph on the large path ([3869679](https://github.com/ozanozbeker/epistole/commit/38696798c4a8a04409a87dd9313f90813ee66a03)), closes [#46](https://github.com/ozanozbeker/epistole/issues/46)
* send over Graph on the small path ([484a232](https://github.com/ozanozbeker/epistole/commit/484a232516aab269a5d8e7b45877d5fa1b0b6854)), closes [#45](https://github.com/ozanozbeker/epistole/issues/45)
* send over SMTP with no credential or a password ([600714b](https://github.com/ozanozbeker/epistole/commit/600714b9059ad7f3f149529275c117020a8520bb)), closes [#43](https://github.com/ozanozbeker/epistole/issues/43)
* send over SMTP with OAuth ([2fea1d4](https://github.com/ozanozbeker/epistole/commit/2fea1d4d1c3a0317848c7bd055f4a8b600dc7c0f)), closes [#47](https://github.com/ozanozbeker/epistole/issues/47)
* send over the Gmail API ([2177623](https://github.com/ozanozbeker/epistole/commit/217762367dab5ecefeeefe11c605b7f7ff70cf07)), closes [#44](https://github.com/ozanozbeker/epistole/issues/44)


### Bug Fixes

* reject a content id that is not ASCII ([5dfffca](https://github.com/ozanozbeker/epistole/commit/5dfffcaf7b031e1b6d8748d0aec13e8129a0baab)), closes [#41](https://github.com/ozanozbeker/epistole/issues/41)
* reject a line break in a subject, address, filename or content id ([76822c7](https://github.com/ozanozbeker/epistole/commit/76822c7e0bfbccb57ee7c3b7f9d8fa2be5efa6b5)), closes [#42](https://github.com/ozanozbeker/epistole/issues/42)


### Documentation

* explain each value in a docstring under it ([6fa644d](https://github.com/ozanozbeker/epistole/commit/6fa644dbd0987a3a2503b5e1562abdb3d98ea9d0))

## [0.0.4](https://github.com/ozanozbeker/epistole/compare/v0.0.3...v0.0.4) (2026-09-23)


### Features

* build and compare a message ([54f8430](https://github.com/ozanozbeker/epistole/commit/54f84303e7d1c11b47f6b65e1e8bbdbc4fbbc55c)), closes [#34](https://github.com/ozanozbeker/epistole/issues/34)
* send a message through MemoryBackend ([57f6518](https://github.com/ozanozbeker/epistole/commit/57f651821f1105a567b261a35a382229a142e737)), closes [#35](https://github.com/ozanozbeker/epistole/issues/35)


### Documentation

* repair the citation and name drift in the spec and the adrs ([fbf7a36](https://github.com/ozanozbeker/epistole/commit/fbf7a36757bbb1f85a75db15dd66244771243b77))
* resolve the v1 spec review findings ([649dcfa](https://github.com/ozanozbeker/epistole/commit/649dcfaa23cc42877d7e71e74f8cd1d76d294c0a))
* rewrite the prose to the writing guidelines ([#49](https://github.com/ozanozbeker/epistole/issues/49)) ([04f9126](https://github.com/ozanozbeker/epistole/commit/04f91261b24fe5ba22f6558bb733a0879123189c))

## [0.0.3](https://github.com/ozanozbeker/epistole/compare/v0.0.2...v0.0.3) (2026-09-10)


### Documentation

* add html authoring guide to readme ([aa8030b](https://github.com/ozanozbeker/epistole/commit/aa8030b34f2d5c0965ebd823bb68ffb4f80cead0))
* collapse the ADRs into the v1 api spec ([25171f6](https://github.com/ozanozbeker/epistole/commit/25171f6ec767e8d80ebaca2e124d5f6e5758a6c0))
* decide how a message carries custom headers ([8203e40](https://github.com/ozanozbeker/epistole/commit/8203e404821e861a3f04857c268be6b8a23d980e))
* decide how an address is written and when it is checked ([9424d34](https://github.com/ozanozbeker/epistole/commit/9424d340db9b2a26b08be488314109546a50d5c4))
* decide what the test backends record ([d9fccd4](https://github.com/ozanozbeker/epistole/commit/d9fccd41840752782be50363d85d59b91fc24841))
* record that css stays as written ([1b65853](https://github.com/ozanozbeker/epistole/commit/1b65853feb3df23d1f602e03360393888eeab24e))
* research css in an html body ([9287a3e](https://github.com/ozanozbeker/epistole/commit/9287a3e97c5bb5e6be940715b20f2baf2cc1cbcf))
* rule live-send verification out of scope ([128d18c](https://github.com/ozanozbeker/epistole/commit/128d18c92acca6a03578e9a9027ef15c514974cb))
* update the package name explanation ([7f1e7b2](https://github.com/ozanozbeker/epistole/commit/7f1e7b23c3d9786ffad8be97607c591be8d3f84d))
* write up the [#8](https://github.com/ozanozbeker/epistole/issues/8) html-body findings ([a5a351e](https://github.com/ozanozbeker/epistole/commit/a5a351e4c3a9f63be13c032ad7140f776856de3d))

## [0.0.2](https://github.com/ozanozbeker/epistole/compare/v0.0.1...v0.0.2) (2026-09-10)


### Features

* rename package from herma to epistole ([a06dce5](https://github.com/ozanozbeker/epistole/commit/a06dce5fa88aadb08188fe7c351cd80f8b2c2f14))


### Documentation

* add contributing guide ([78285cd](https://github.com/ozanozbeker/epistole/commit/78285cd520561c1e0a269425049a7ba35ac49180))
* add prose spelling rule to CONTRIBUTING ([eaaa749](https://github.com/ozanozbeker/epistole/commit/eaaa74998d66870fe3161bfb13d087bea6b0a968))
* add wayfinder research findings ([354a182](https://github.com/ozanozbeker/epistole/commit/354a182da4bdb8276bdb4fb466fc25f7ddb197ab))
* record attachment and inline-image decisions ([33c96c7](https://github.com/ozanozbeker/epistole/commit/33c96c7443e2659bd62c96760d9f520a61244a2d))
* record backend connection lifecycle ([4c4dd75](https://github.com/ozanozbeker/epistole/commit/4c4dd75cb5ccd21b84269002ff041d6a4d6a13fe))
* record credentials as values in each backend module ([bc17259](https://github.com/ozanozbeker/epistole/commit/bc17259a5d7eb563fadde011afbfef42ec09246b))
* record graph as json on two paths chosen by size ([7caa2c1](https://github.com/ozanozbeker/epistole/commit/7caa2c1c2306eb853ab01f9e0f32fb6700d081e5))
* record how a backend plugs into a message ([5b9b4d8](https://github.com/ozanozbeker/epistole/commit/5b9b4d82d4c184fbcb4a389d5c121058a0f8d476))
* record message immutability and chaining semantics ([0777d05](https://github.com/ozanozbeker/epistole/commit/0777d0568219f6b5b64cd4bf554b8ef6c4ded0e3))
* record plain-text derivation and content entries ([8ca885a](https://github.com/ozanozbeker/epistole/commit/8ca885ac4af6c2f3873da3aabe80a364cd33a98e))
* record receipt and error model ([1e97e22](https://github.com/ozanozbeker/epistole/commit/1e97e22843a37940f0a96a8d0cf6c403a1fb49c8))
* record that herma has no escape hatch and no unsupported-feature mechanism ([489c5b3](https://github.com/ozanozbeker/epistole/commit/489c5b3f4f05c3349d10f694f6a8daba26ff9459))
* record the HTTP backend dependency and transport strategy ([bf004a6](https://github.com/ozanozbeker/epistole/commit/bf004a60c0cfabade67ed30cce807c87e76b21c2))
* settle the domain vocabulary ([babbed2](https://github.com/ozanozbeker/epistole/commit/babbed2a82962a0d367ce0a7e27802f363dbdd44))
