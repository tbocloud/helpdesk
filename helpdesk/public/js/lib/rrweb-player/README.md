# rrweb-player (vendored)

- Package: [rrweb-player](https://www.npmjs.com/package/rrweb-player) **2.1.6** (MIT, see `LICENSE`)
- Source: `https://registry.npmjs.org/rrweb-player/-/rrweb-player-2.1.6.tgz`
  (npm shasum `fc33bf37aa8ddaed433f4056e07af86c2e0ec63f`)
- Files:
  - `rrweb-player.min.js` — `package/umd/rrweb-player.min.js` (UMD; exposes `window.rrwebPlayer.default`)
  - `style.min.css` — `package/dist/style.min.css`
  - The trailing `sourceMappingURL` comments were removed (the maps are not vendored).

The agent ticket view (`desk/src/composables/sessionReplay.ts`) loads these lazily
from `/assets/helpdesk/js/lib/rrweb-player/` only when an agent opens a session
replay, so the player is not part of the desk bundle and needs no `yarn install`.
The player's major version must match the rrweb recorder in `helpdesk_client`.

To upgrade: download the new tarball, copy the two files above, strip the
`sourceMappingURL` comments, and bump the version here and in `sessionReplay.ts`.
