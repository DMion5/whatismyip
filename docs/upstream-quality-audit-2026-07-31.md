# Upstream performance and quality-of-life audit

Date: 2026-07-31

Compared:

- Fork base: `bce429c`
- Original upstream repository: `unc-network/whatismyip` `master` at `e82fdfb`
- Fork branch: `codex/my-ip-rebrand`

The upstream branch had 66 commits after the shared base: 55 content commits and
11 merge commits. Every content commit was reviewed. Runtime improvements were
adapted to the fork's My IP and University at Buffalo configuration; upstream
release notes, repository naming, licensing, and institution-specific
documentation were not copied.

## Content commit disposition

| Commit | Upstream subject | Disposition |
| --- | --- | --- |
| `fee8ea9` | minor ordering and display updates | Applied; retained the fork's page structure and UB labels. |
| `1b28e65` | documentation cleanup | Reviewed; not copied because it only reorganizes upstream documentation. |
| `c8542d1` | add network contact | Applied to the campus network details. |
| `d0411d2` | metrics optimization | Applied with cache scoping added for multiple databases/windows. |
| `1b3af03` | fix intro text overwrite | Applied. |
| `db3b39b` | chart breakdown by ip version | Applied with UB chart colors. |
| `b84e37a` | chart tweak for version split | Applied. |
| `ebbc3b5` | trend line stacking tweak | Applied. |
| `eecccd8` | add metrics page view counting | Applied. |
| `a781cbd` | changelog fix | Reviewed; superseded by this fork's changelog entry. |
| `cc45424` | max chart hight | Applied. |
| `f081914` | fix intro text getting wiped | Applied; preserved with the later related fix. |
| `96cd87f` | change log update | Reviewed; superseded by this fork's changelog entry. |
| `b6fa9dc` | count optimization | Applied using a single aggregate totals query. |
| `2dcf95a` | change log update | Reviewed; superseded by this fork's changelog entry. |
| `eda5bf0` | fix metrics for theme switching and colors | Applied with UB light/dark palettes. |
| `677f581` | sql database optimization for metrics | Applied; metrics queries use an in-memory SQLite backup. |
| `38f6fe7` | database tweak | Applied as part of the final metrics schema/query state. |
| `b467979` | add max retention days for metrics | Applied and made configurable in `config.toml`. |
| `a8f1794` | change log update | Reviewed; superseded by this fork's changelog entry. |
| `374c2c9` | black formatting fix | Applied where it affected retained Python code. |
| `1c1a221` | fix tests for database changes | Adapted and expanded with retention, cache isolation, and IP-version tests. |
| `651734b` | Example env update for metrics config | Applied; metrics window/retention settings now live in `config.toml`. |
| `553bab5` | add vpn and ssid info | Applied; VPN CIDRs also participate in campus classification. |
| `00df1bb` | button fixes | Applied. |
| `d511c5e` | add status page info to connectivity page | Applied as an optional configured integration. |
| `b5f443a` | slight reordering of connectivity page | Applied while retaining UB help links. |
| `a262aef` | exclude maintenance items on status | Applied. |
| `2a1c098` | first pass at accessibility review items | Applied. |
| `3f6628c` | fix more accessibility review items | Applied, including map and status accessibility. |
| `2377564` | update change log | Reviewed; superseded by this fork's changelog entry. |
| `e4fd12b` | accessibility tweaks | Applied. |
| `7eb89a2` | version and changelog update | Adapted as fork version `1.11.0`; upstream release text was not copied. |
| `251976f` | icloud and proxy feedback testing | Applied. |
| `76aa733` | fix icloud check in org/isp fields | Applied. |
| `e1c3164` | fix inaccurate nat detection with icloud relay | Applied. |
| `4ec2dfe` | javascript function name cleanup | Applied. |
| `3478311` | variable cleanup | Applied. |
| `b496e59` | race case tweaks on javascript checks | Applied. |
| `dbcc5f8` | javascript logic cleanup on additional checks | Applied. |
| `8479898` | fix button link text | Applied. |
| `dda8431` | add vpn group and network purpose display | Applied. |
| `2757a1f` | move divs from dynamic creation into base html | Applied for stable layout and accessible live regions. |
| `e89961b` | javascript variable cleanup | Applied; an additional leaked temporary variable was also scoped. |
| `90d5a2a` | changelog update | Reviewed; superseded by this fork's changelog entry. |
| `cb3992e` | name clarification | Not copied; it changes upstream repository naming/licensing rather than runtime quality. |
| `332d4bd` | footer color fix | Applied with UB colors. |
| `31db72f` | link color css fix | Applied with UB colors and contrast. |
| `2f3ac33` | changelog update for fix | Reviewed; superseded by this fork's changelog entry. |
| `2337fbd` | Accessibility updates | Applied. |
| `3fbc6c9` | add documentation | Reviewed; upstream contributor/AI documentation is not required at runtime. |
| `68ae3df` | fix documentation | Reviewed; upstream-only documentation. |
| `eb09e5e` | update for accessibility review result | Reviewed; report/documentation commit, with its runtime recommendations already applied. |
| `0865b2c` | update change log for accessibility review | Reviewed; superseded by this fork's changelog entry. |
| `44913ec` | add documentation | Reviewed; upstream-only documentation/version metadata. |

## Merge commits

The following 11 merge commits contain no independent change beyond the content
commits above and were therefore reviewed through their merged diffs:
`4112b15`, `85ef82f`, `c89d8ea`, `5de9a41`, `7780cb4`, `0866f85`,
`818e83f`, `ee9fb10`, `471ca62`, `1c10194`, and `e82fdfb`.

## Fork-specific safeguards

- No original-institution names, domains, CSS variables, or simulated campus
  data were introduced.
- My IP naming, the neutral placeholder logo/favicon, UB links, and the IPv6
  under-construction notice remain in place.
- VPN detection works without an IPAM result and reports network purpose `VPN`.
- Metrics cache entries cannot leak between application instances that use
  different SQLite databases or reporting windows.
