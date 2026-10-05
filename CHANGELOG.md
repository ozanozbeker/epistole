# Changelog

## [0.0.7](https://github.com/ozanozbeker/epistole/compare/v0.0.6...v0.0.7) (2026-10-05)


### Bug Fixes

* count each addr-spec once in Gmail's recipient check, and drop Graph's ([#111](https://github.com/ozanozbeker/epistole/issues/111)) ([25ae8a1](https://github.com/ozanozbeker/epistole/commit/25ae8a16334b09a5a93a91986e6ff9c0cf6d5ce0)), closes [#96](https://github.com/ozanozbeker/epistole/issues/96)
* let a get_token error propagate unchanged on every backend ([#109](https://github.com/ozanozbeker/epistole/issues/109)) ([d48ae77](https://github.com/ozanozbeker/epistole/commit/d48ae777c2df032e95d57eb5568cd225c2dd1852))
* map a discovery reply that msal cannot read or that rejects the credential ([#117](https://github.com/ozanozbeker/epistole/issues/117)) ([9f5de72](https://github.com/ozanozbeker/epistole/commit/9f5de72928b3390b90922d84f1d34e501b20082b))
* map a token reply without an access token to ProviderError ([#115](https://github.com/ozanozbeker/epistole/issues/115)) ([a3e2d21](https://github.com/ozanozbeker/epistole/commit/a3e2d21d6ce43d1698f67c9c22629d8494d0522f))
* request a new Gmail token after a failed 401 refresh ([#110](https://github.com/ozanozbeker/epistole/issues/110)) ([98bb9b8](https://github.com/ozanozbeker/epistole/commit/98bb9b85af4e7dfd1a1bee42a4e342ae1cd7ce20)), closes [#100](https://github.com/ozanozbeker/epistole/issues/100)
* send a certificate's client assertion as a JWT ([#119](https://github.com/ozanozbeker/epistole/issues/119)) ([ef27a01](https://github.com/ozanozbeker/epistole/commit/ef27a0106afc927afebad7734e85ec3d804397cd))
* word token errors the same way on Gmail and Graph ([#114](https://github.com/ozanozbeker/epistole/issues/114)) ([e604246](https://github.com/ozanozbeker/epistole/commit/e60424687922274232e505cdbf695dea5ee5bcaa))


### Documentation

* point live-send references at the open tickets ([#94](https://github.com/ozanozbeker/epistole/issues/94)) ([3a17bdf](https://github.com/ozanozbeker/epistole/commit/3a17bdfc114c828745e1bfafc63176afeae40124))

## [0.0.6](https://github.com/ozanozbeker/epistole/compare/v0.0.5...v0.0.6) (2026-09-30)


### Documentation

* color the site from a stylesheet in assets ([#87](https://github.com/ozanozbeker/epistole/issues/87)) ([70ac733](https://github.com/ozanozbeker/epistole/commit/70ac733329e3df05595abe3cac9f72110375dc9a))
* move the README's guide into site pages ([#85](https://github.com/ozanozbeker/epistole/issues/85)) ([d61a006](https://github.com/ozanozbeker/epistole/commit/d61a006a22f704c83946174ebb8e359407d202c2)), closes [#77](https://github.com/ozanozbeker/epistole/issues/77)
* write the setup steps for each mail service ([#89](https://github.com/ozanozbeker/epistole/issues/89)) ([ae67bf0](https://github.com/ozanozbeker/epistole/commit/ae67bf04fd8b6fac7019e7d7dbd06c18f1bee76f)), closes [#78](https://github.com/ozanozbeker/epistole/issues/78)

## [0.0.5](https://github.com/ozanozbeker/epistole/compare/v0.0.4...v0.0.5) (2026-09-30)


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

* authenticate a Password through one SMTP mechanism ([16bccba](https://github.com/ozanozbeker/epistole/commit/16bccba695655f2f3168fcf97a5a80549d6b74c9)), closes [#71](https://github.com/ozanozbeker/epistole/issues/71)
* declare __all__ in epistole.exceptions ([0aa43b5](https://github.com/ozanozbeker/epistole/commit/0aa43b5433b6ae091e3131ab1650882200cf87ea))
* make one attempt per Gmail token request ([db0c21e](https://github.com/ozanozbeker/epistole/commit/db0c21ea2196fe486c96dc37c46f74ae6cdd077e)), closes [#52](https://github.com/ozanozbeker/epistole/issues/52)
* map a Graph token reply by its status ([69a565a](https://github.com/ozanozbeker/epistole/commit/69a565afdfec1edb28cf8ca4ca912cdb33b14e5f)), closes [#63](https://github.com/ozanozbeker/epistole/issues/63)
* map a null or empty draft id or uploadUrl to ProviderError ([870f3a9](https://github.com/ozanozbeker/epistole/commit/870f3a9cebb7e3ed1531405f291f224a20e976a1)), closes [#56](https://github.com/ozanozbeker/epistole/issues/56)
* map a token reply google-auth or msal cannot read to ProviderError ([d9de3cc](https://github.com/ozanozbeker/epistole/commit/d9de3cc0f5d31a84f358b9a7d744affcd646c292)), closes [#55](https://github.com/ozanozbeker/epistole/issues/55)
* name the from address's domain in EHLO ([#82](https://github.com/ozanozbeker/epistole/issues/82)) ([846d705](https://github.com/ozanozbeker/epistole/commit/846d705e6c4b20c9f90cf095a0cd66248cfae136))
* raise RejectedError for a custom Resent-Bcc over SMTP ([797a415](https://github.com/ozanozbeker/epistole/commit/797a415648e21e431c03112e90877adf1b5f5b43)), closes [#57](https://github.com/ozanozbeker/epistole/issues/57)
* raise ValueError for a custom Resent-Bcc on every backend ([cf47954](https://github.com/ozanozbeker/epistole/commit/cf47954061b7e3f17555fe26bb4469b171122a8e)), closes [#64](https://github.com/ozanozbeker/epistole/issues/64)
* raise ValueError for a surrogate in any text a caller passes ([4adbd4e](https://github.com/ozanozbeker/epistole/commit/4adbd4e3052edece49f0a3e0adc13a6dc933e6a1)), closes [#59](https://github.com/ozanozbeker/epistole/issues/59)
* raise when an &lt;img src&gt; names a cid: that no inline image holds ([d682378](https://github.com/ozanozbeker/epistole/commit/d68237806e4fc5adee3230f2a9c72c25517f1b55))
* reject a content id that is not ASCII ([5dfffca](https://github.com/ozanozbeker/epistole/commit/5dfffcaf7b031e1b6d8748d0aec13e8129a0baab)), closes [#41](https://github.com/ozanozbeker/epistole/issues/41)
* reject a line break in a subject, address, filename or content id ([76822c7](https://github.com/ozanozbeker/epistole/commit/76822c7e0bfbccb57ee7c3b7f9d8fa2be5efa6b5)), closes [#42](https://github.com/ozanozbeker/epistole/issues/42)
* request a token on every connect() for an AuthorizedUser ([654c2ab](https://github.com/ozanozbeker/epistole/commit/654c2abcf3184b19330021f2ed9663ec85f99da2)), closes [#53](https://github.com/ozanozbeker/epistole/issues/53)
* resolve the loose ends from the [#48](https://github.com/ozanozbeker/epistole/issues/48) audit ([7807781](https://github.com/ozanozbeker/epistole/commit/7807781181547d38601a53da919cea31bee497d4)), closes [#62](https://github.com/ozanozbeker/epistole/issues/62)
* write UTF-8 headers for a non-ASCII custom header value ([483cd94](https://github.com/ozanozbeker/epistole/commit/483cd94c9f963ce42f654fbec0f10c7ecd7ed4ae)), closes [#58](https://github.com/ozanozbeker/epistole/issues/58)


### Documentation

* decide how the code resolves the loose ends from the [#48](https://github.com/ozanozbeker/epistole/issues/48) audit ([3502596](https://github.com/ozanozbeker/epistole/commit/3502596ad932aef6ff3ad15a4f7c58743212c26c)), closes [#62](https://github.com/ozanozbeker/epistole/issues/62)
* decide that a custom Resent-Bcc is a ValueError on every backend ([dbd98a6](https://github.com/ozanozbeker/epistole/commit/dbd98a65431a583ac89122b2ec2325b27d30853f)), closes [#64](https://github.com/ozanozbeker/epistole/issues/64)
* decide that a non-ASCII custom header value needs UTF-8 headers ([4680a58](https://github.com/ozanozbeker/epistole/commit/4680a58357d285891ef197ca0bd16e83b31cf2cd)), closes [#58](https://github.com/ozanozbeker/epistole/issues/58)
* decide that a null or empty draft id or uploadUrl is ProviderError ([8aa901c](https://github.com/ozanozbeker/epistole/commit/8aa901c4ebe3f77112209e0bd2c8005decae2ab3)), closes [#56](https://github.com/ozanozbeker/epistole/issues/56)
* decide that a surrogate is a ValueError wherever a caller passes text ([6ba3d71](https://github.com/ozanozbeker/epistole/commit/6ba3d712b78ab3d76838c526d96957cbb3e8bcf6)), closes [#59](https://github.com/ozanozbeker/epistole/issues/59)
* decide that an unreadable token reply is ProviderError ([3978c4b](https://github.com/ozanozbeker/epistole/commit/3978c4b3f943fe798964dd7cebdab7e103b6be00)), closes [#55](https://github.com/ozanozbeker/epistole/issues/55)
* decide that connect() ignores a saved AuthorizedUser token ([8f5fa7d](https://github.com/ozanozbeker/epistole/commit/8f5fa7d8dd7416766534a10fd51bc3c9cb2a7a5c)), closes [#53](https://github.com/ozanozbeker/epistole/issues/53)
* decide that Gmail makes one attempt per token request ([ecfd45e](https://github.com/ozanozbeker/epistole/commit/ecfd45ef28794a5cc459139f3453b8ea3bb5522a)), closes [#52](https://github.com/ozanozbeker/epistole/issues/52)
* decide that Graph maps a token reply by its status ([6b41d93](https://github.com/ozanozbeker/epistole/commit/6b41d939bf6b0d801f46b50bd66a4f559ac4df54)), closes [#63](https://github.com/ozanozbeker/epistole/issues/63)
* decide that SMTP raises RejectedError on a custom Resent-Bcc ([7409ffd](https://github.com/ozanozbeker/epistole/commit/7409ffd125c652c81d7ca66a5df637194a9b9857)), closes [#57](https://github.com/ozanozbeker/epistole/issues/57)
* define mail service in the glossary ([#84](https://github.com/ozanozbeker/epistole/issues/84)) ([56812c4](https://github.com/ozanozbeker/epistole/commit/56812c4b8a3636d802bba2947a0ee33dfdaeba86))
* explain each value in a docstring under it ([6fa644d](https://github.com/ozanozbeker/epistole/commit/6fa644dbd0987a3a2503b5e1562abdb3d98ea9d0))
* record that Epistole does not accept a domain-literal address ([a00762e](https://github.com/ozanozbeker/epistole/commit/a00762eeacc7f937dfa27ecb05aff87d435b7e39)), closes [#65](https://github.com/ozanozbeker/epistole/issues/65)
* record that the README shows no example for every public name ([3fd05ad](https://github.com/ozanozbeker/epistole/commit/3fd05ade445b8c3e19e09286300790a83ee0251b))
* record what implementing [#62](https://github.com/ozanozbeker/epistole/issues/62) measured ([4b6188a](https://github.com/ozanozbeker/epistole/commit/4b6188a7be6bddd63e016acd24f35f187f58b28c))
* record what implementing [#63](https://github.com/ozanozbeker/epistole/issues/63) measured ([17572ee](https://github.com/ozanozbeker/epistole/commit/17572ee5959330158578764316ed23e290451cfd))
* record what the iCloud live sends measured ([91f4daa](https://github.com/ozanozbeker/epistole/commit/91f4daa613e5a88ac1378a76b40496ee1a0ea50d)), closes [#66](https://github.com/ozanozbeker/epistole/issues/66)
* run every README example against MemoryBackend ([9d188bb](https://github.com/ozanozbeker/epistole/commit/9d188bb2f2400baca135ef27522de721e80555f9)), closes [#48](https://github.com/ozanozbeker/epistole/issues/48)

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
