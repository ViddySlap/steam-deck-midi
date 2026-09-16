# Reference imagery - Valve's own Steam Deck product renders

Fetched 2026-09-15 from Valve's official Steam Deck site (steamdeck.com tech specs page,
https://www.steamdeck.com/en/tech/deck), which serves these renders from Valve's own CDN.

| file | source URL | sha256 | size |
|---|---|---|---|
| steamdeck-tech-specs-front.png | https://cdn.fastly.steamstatic.com/steamdeck/images/tech-specs/tech-specs_1_english.png?v=2 | 56f3107c84bc1e91bfcbba71cad63540f12cf7a6d70105f7d4697acb50d592c0 | 2208x1224 |
| steamdeck-tech-specs-top.png | https://cdn.fastly.steamstatic.com/steamdeck/images/tech-specs/tech-specs_2_english.png?v=2 | 8b9052bed0e5ccd6bca6fbba289a988360a3e958e145809062b68a025a43dbe5 | 2208x624 |
| steamdeck-tech-specs-rear.png | https://cdn.fastly.steamstatic.com/steamdeck/images/tech-specs/tech-specs_3_english.png?v=2 | e87caecf3628aa0761d2930f0598fc1f2aa3ebc1d897cee3f135315c12cf5615 | 2208x1224 |

These are Valve's artwork, kept here ONLY as the reference the arrangement was checked
against. Nothing in windows/static/controller/ embeds or traces them; steam_deck.svg
remains an original geometric drawing.

Fetch command used (per file, n = 1, 2, 3):

    curl -sS -o tech-specs_${n}_english.png \
      "https://cdn.fastly.steamstatic.com/steamdeck/images/tech-specs/tech-specs_${n}_english.png?v=2"

Verify:

    shasum -a 256 -c docs/sdpolish-p2/reference/SHA256SUMS
