# DESIGN.md — assistant/settings: the natural-language settings editor (issue #120)

This document specifies and records the implemented design of
`assistant/settings/`: the tool registry, the parser/planner/applier
pipeline, the generated-registry pipeline underneath it, and the in-shell
QML integration. Every factual claim about the shell's schema below was
verified against the sources in the checkout this module was built against;
the commands and their real outputs are condensed in the "Verified
citations" appendix. Citations are referenced inline as `[Cn]`.

---

## 0. What this module is (and is not)

`assistant/settings/` is a fifth, clearly separated module next to the four
troubleshooting layers (diagnostics, retrieval, generative, issues). It closes
the gap issue #120 asks for:

    NL text → Intent Parser → Structured Tool Calls → validated application

to the shell configuration. The four existing layers answer "what is broken";
this module answers "change this setting".

Pipeline:

    text ──parser.py──▶ ops (pure, no I/O)
    ops ──planner.py──▶ plan (reads current values from the target file,
                         type-checks, range-checks, resolves relative ops)
    plan ──applier.py──▶ written file (ONLY behind the explicit --apply gate;
                         dry-run is the default)

Target of every write: the GLOBAL shell config file

    ~/.config/caelestia/shell.json        (`configDir()/shell.json`, [C7][C8])

Per-screen override files (`~/.config/caelestia/monitors/<screen>/shell.json`,
[C7][C9]) are **out of scope** — never read for writing, never
written. The planner performs one *read-only, best-effort* check of them to warn
when a global write will be shadowed (§4.6); that is all.

The running shell hot-reloads external edits to shell.json (QFileSystemWatcher +
50 ms load debounce + 3 retries for partial writes, [C10]), so a write to the
watched file is applied "through Caelestia's existing configuration system":
final schema validation, type decoding, quarantine of unknown/ill-typed keys
([C23]) and the live UI update all stay inside Caelestia's own settings layer.
There is no settings IPC to call instead — the shell's IPC surface exposes
no settings setter (`shell.qml` itself registers only the `region` and
`lock` handlers, [C19]) — the watched file is the only external entry into
the live config system.

---

## 1. Tool registry (18 tools)

`registry.py` holds a single frozen list of `ToolSpec` dataclasses: the 18
everyday tools that answer plain natural-language words, each grounded the
same way — C++ declaration + shipped Nexus control + live QML reader (see
§16 for the full evaluation of what else was considered and left out):

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str            # tool name, e.g. "setBarScale"
    path: str            # dotted JSON path in shell.json, e.g. "bar.scale"
    kind: str            # "float" | "int" | "bool" | "enum"
    default: float | int | bool | str
    minimum: float | int | None      # None for bool/enum
    maximum: float | int | None
    enum: tuple[str, ...] | None     # ("top","bottom","left","right") for position
    global_only: bool     # SETTINGS_GLOBAL_PROPERTY upstream (see [C6])
    step: float | int     # magnitude of one "step" op (never used for bool/enum)
    nouns: tuple[str, ...]           # parser nouns (§3.4)
```

| # | tool | JSON path | JSON type | validation | default | globalOnly? | citation (C++ property + QML evidence) |
|---|------|-----------|-----------|------------|---------|-------------|----------------------------------------|
| 1 | `setBarScale` | `bar.scale` | number (float) | 0.6 – 1.6 | 1.0 | no | `barconfig.hpp:233` `CONFIG_PROPERTY(qreal, scale, 1.0)`; QML floor 0.6 `BarWrapper.qml:24`; upstream UI stepper 0.6–1.6 `TaskbarPanel.qml:161-165` [C1][C12][C13] |
| 2 | `setBarPosition` | `bar.position` | string | enum top/bottom/left/right | `"bottom"` | no | `barconfig.hpp:262` `CONFIG_PROPERTY(QString, position, u"bottom"_s)`; consumed as 4-way `BarWrapper.qml:23,33-39,166-215` [C1][C12] |
| 3 | `setDockIconSize` | `bar.dock.iconSize` | number (int) | 16 – 96 | 32 | no | `barconfig.hpp:174` `CONFIG_PROPERTY(int, iconSize, 32)`; QML floor 16 `Dock.qml:38`; upstream UI stepper `BarDock.qml:54-63` [C1][C16] |
| 4 | `setBarPersistent` | `bar.persistent` | bool | true/false | true | no | `barconfig.hpp:246`; readers `BarWrapper.qml:27,62`; UI toggle `TaskbarPanel.qml:71-72` [C1][C2] |
| 5 | `setLivePreviews` | `bar.livePreviews` | bool | true/false | true | no | `barconfig.hpp:239-243` (comment ties it to the NVIDIA + KWin screencast freeze); UI toggle with the same warning `TaskbarPanel.qml:178-183`; readers `WindowPreview.qml:42`, `AmbientGlow.qml:120` [C1][C13] |
| 6 | `setBlurEnabled` | `appearance.blur` | bool | true/false | true | **yes** | `appearanceconfig.hpp:233` `CONFIG_GLOBAL_PROPERTY(bool, blur, true)`; UI toggle `AppearancePage.qml:222-235`; live blur region `WindowFactory.qml:64` [C3][C14][C30] |
| 7 | `setTransparencyBase` | `appearance.transparency.base` | number (float) | 0.0 – 1.0 | 0.85 | **yes** | `appearanceconfig.hpp:216` `CONFIG_GLOBAL_PROPERTY(qreal, base, 0.85)`; UI slider "Base opacity" `AppearancePage.qml:141-148`; slider clamps 0..1 `SliderRow.qml:103-109`; it is the surface opacity `ContentWindow.qml:383` [C3][C14][C15][C27] |
| 8 | `setRoundingScale` | `appearance.rounding.scale` | number (float) | 0.5 – 2.0 | 1 | no | `appearanceconfig.hpp:21` (class `AppearanceRounding`); UI stepper 0.5–2.0 `AppearancePage.qml:118-126`; token-multiplier semantics `appearanceconfig.cpp:32-33` [C3][C14] |
| 9 | `setSpacingScale` | `appearance.spacing.scale` | number (float) | 0.5 – 2.0 | 1 | no | `appearanceconfig.hpp:56`; UI stepper 0.5–2.0 `AppearancePage.qml:296-304` [C3][C14] |
| 10 | `setPaddingScale` | `appearance.padding.scale` | number (float) | 0.5 – 2.0 | 1 | no | `appearanceconfig.hpp:89`; UI stepper 0.5–2.0 `AppearancePage.qml:306-314` [C3][C14] |
| 11 | `setFontScale` | `appearance.font.scale` | number (float) | 0.5 – 2.0 | 1 | no | `appearanceconfig.hpp:154`; UI stepper 0.5–2.0 `AppearancePage.qml:285-294` [C3][C14] |
| 12 | `setAnimationSpeed` | `appearance.anim.durations.scale` | number (float) | 0.25 – 4.0 | 1 | **yes** | `appearanceconfig.hpp:172` `CONFIG_GLOBAL_PROPERTY(qreal, scale, 1)` (class `AnimDurations`); UI stepper 0.25–4.0 `AppearancePage.qml:316-325`; durations are multiplied by it (`AnimatedPasswordMask.qml:116`, `CircularIndicator.qml:68,95,104`) → **lower = faster** [C3][C14][C26] |
| 13 | `setBorderThickness` | `border.thickness` | number (int) | 0 – 50 | 10 | no | `borderconfig.hpp:13` `CONFIG_PROPERTY(int, thickness, 10)`; UI stepper 0–50 ("Set to 0 for a borderless look") `AppearancePage.qml:108-115`; C++ clamps to `minThickness()==2` in some consumers `borderconfig.hpp:21-23` [C4][C14] |
| 14 | `setLauncherMaxShown` | `launcher.maxShown` | number (int) | 1 – 20 | 7 | no | `launcherconfig.hpp:44` `CONFIG_PROPERTY(int, maxShown, 7)`; UI stepper 1–20 `LauncherPanel.qml:139-146`; readers `AppList.qml:86`, `KeybindsList.qml:77`, `AnimationsList.qml:74` [C5][C17] |
| 15 | `setPitchBlack` | `appearance.pitchBlack` | bool | true/false | false | **yes** | `appearanceconfig.hpp:231` `CONFIG_GLOBAL_PROPERTY(bool, pitchBlack, false)`; UI toggle "Bezel mode (Pitch black)" `AppearancePage.qml:92-99`; readers `ContentWindow.qml:383,394`, `BadAppleOverlay.qml:45`, `Menu.qml:155` [C31] |
| 16 | `setNotifsMaxPopups` | `notifs.maxPopups` | number (int) | 0 – 30 | 8 | **yes** | `notifsconfig.hpp:24` `CONFIG_GLOBAL_PROPERTY(int, maxPopups, 8)`; UI stepper 0–30 `NotificationPreferencesPage.qml:137-145`; live reader `notifications/Content.qml:85` [C18][C32] |
| 17 | `setNotifsMaxNotifs` | `notifs.maxNotifs` | number (int) | 20 – 2000 | 50 | **yes** | `notifsconfig.hpp:25` `CONFIG_GLOBAL_PROPERTY(int, maxNotifs, 50)`; UI stepper 20–2000 `NotificationPreferencesPage.qml:147-156`; live reader `services/Notifs.qml:27` [C18][C32] |
| 18 | `setDockBadges` | `bar.dock.showBadges` | bool | true/false | true | no | `barconfig.hpp:173` `CONFIG_PROPERTY(bool, showBadges, true)` (plain `ObjectNode` child of Bar — per-bar, NOT global-only); UI toggle "Show app badges" `BarDock.qml:75-82`; live reader `Dock.qml:630-634` (`?? true`-null-safe `badge` over `LauncherEntry.forApp`); badge visuals `Dock.qml:469,673-706,708-726`; release note whatsnew `dock_app_badges` [C36] |

### 1.1 Ranges are the assistant's own conservative validation — stated plainly

Upstream declares **no numeric bounds in the schema** for any of these keys
(`CONFIG_PROPERTY(qreal, scale, 1)` etc. carry only a type and a default — see
[C1][C3][C4][C5]; the property setter's validation hook, `macros.hpp:91-92`,
is type-only — `if (rejectInvalidWrite(...)) return; /* Skip writes of the
wrong type */` — and still a no-op for every ordinary typed property, since
the template overload returns false unconditionally, node.hpp:88-92; only
the new QVariant-union keys get a metatype check, node.cpp:133-141, [C6]).
The only hard upstream limits found are:

- `bar.scale` QML floor 0.6 (`BarWrapper.qml:24`, [C12]);
- `bar.dock.iconSize` QML floor 16 (`Dock.qml:38`, [C16]);
- `border.thickness` C++ clamp to ≥ 2 in `clampedThickness()` for some readers
  (`borderconfig.hpp:21-23`, [C4]) — while the UI still writes 0 for "borderless".

So every range in the table above is **the assistant's own validation, chosen
conservative on purpose**, implementing #120's "If a value falls outside the
supported range, it simply isn't applied". Wherever upstream's own shipped UI
exposes a stepper range, the assistant adopts that exact range — this is why the
ranges are 0.6–1.6 / 0.5–2.0 / 0.25–4.0 / 0–50 / 1–20 rather than wider invented
ones (see appendix [C13][C14][C16][C17]; deviations from the orchestrator's
draft ranges are listed in §1.3). One-line rationale per range:

- `bar.scale` 0.6–1.6: QML floor 0.6 + the shipped Nexus stepper's exact range.
- `bar.position` enum: the four states BarWrapper actually implements.
- `bar.dock.iconSize` 16–96: QML floor 16; 96 is a conservative fixed cap
  (upstream's upper stepper bound is dynamic — the bar's inner width).
- bools: no magnitude exists upstream; on/off only.
- `appearance.transparency.base` 0.0–1.0: the UI slider's own 0..1 clamp.
- scale tools 0.5–2.0: the shipped Nexus steppers' exact range.
- `appearance.anim.durations.scale` 0.25–4.0: the shipped stepper's exact range.
- `border.thickness` 0–50: the shipped stepper's exact range (0 = borderless).
- `launcher.maxShown` 1–20: the shipped stepper's exact range.
- `appearance.pitchBlack`: bool — on/off only, no magnitude upstream.
- `bar.dock.showBadges`: bool — on/off only, no magnitude upstream (the
  shipped control is a plain ToggleRow, [C36]).
- `notifs.maxPopups` 0–30 / `notifs.maxNotifs` 20–2000: the shipped
  notification-preferences steppers' exact ranges (`NotificationPreferencesPage.qml:142-143,152-153`, [C32]); their steps (1 / 50) are the steppers' own step sizes.

### 1.2 Default steps (for "step" ops, §3.4)

`scales ±0.1` (tools 1, 8, 9, 10, 11), `transparencyBase ±0.05` (7),
`animationSpeed ±0.25` (12), `iconSize ±4` (3), `borderThickness ±2` (13),
`maxShown ±1` (14), `maxPopups ±1` (16), `maxNotifs ±50` (17 — the shipped
stepper's own step size). Bools and the position enum have no step. These are
the assistant's notion of "one spoken nudge" and are deliberately coarser
than the UI's fine stepper increments (0.05/0.1/2/1) so that "thinner" is
visible.

### 1.3 Deviations from the orchestrator's candidate set (with reasons)

- **Dropped `setDockCentered` (`bar.dock.monitorCenter`)** — the key exists in
  the schema (`barconfig.hpp:171`, default true, [C1][C2]) but **nothing in
  this port reads it**: the only non-header occurrence of `monitorCenter` in the
  whole `shell/` tree is a comment in `Workspaces.qml:26` ("Removed manual
  monitorCenter logic as it's handled natively by Bar.qml layout zones", [C20]).
  Writing an inert key would violate this module's rule that every tool maps to
  a live, observable setting. The honest #120 mapping for "dock position" is
  §2.2 instead.
- **Added `setBorderThickness`** (from `borderconfig.hpp`, permitted source):
  grounded header + stepper + multiple QML readers.
- **Added `setLauncherMaxShown`** (from `launcherconfig.hpp`, permitted source):
  grounded header + stepper + three QML readers. These two brought the
  original everyday set to 14, kept deliberately small — "a handful of
  common actions" in spirit, one screen of `--list-tools` output. Four more
  everyday tools were added later under the same grounding bar (bezel mode,
  notification counts, app badges), for the 18 in §1's table today.
- **Range corrections vs the draft**: `bar.scale` 0.6–1.6 (draft said 2.0),
  rounding/spacing/padding 0.5–2.0 (draft: 0.0–3.0 / 0.25–3.0), font 0.5–2.0
  (draft: 2.5) — all now exactly the shipped UI stepper ranges, which is
  stricter than the draft and grounded in evidence rather than invented.
- **globalOnly correction**: `appearance.anim.durations.scale` is
  `CONFIG_GLOBAL_PROPERTY` (`appearanceconfig.hpp:172`, [C3]) — the draft did
  not mark it global-only. Consequence: per-monitor files may not override it
  (the loader quarantines global-only keys found in overlay files,
  `objectnode.cpp:144-147`, [C23]), so the planner's monitor-override warning
  (§4.6) is skipped for tools 6, 7 and 12.

Candidates examined and rejected (documented so the decision is not
re-litigated):

- `bar.workspaces.shown` — grounded, but **owned by a runtime sync loop**: the
  Nexus page writes it *and* creates/removes KWin virtual desktops to match
  (`BarWorkspaces.qml:34-51`, [C28]); an external write would be half an
  operation and then overwritten by the next Kwin sync. (The same applies to
  `bar.workspaces.monitorCenter`, `barconfig.hpp:44` — like
  `bar.dock.monitorCenter` above, nothing reads it; the only non-header hit
  is the `Workspaces.qml:26` comment, [C20].)
- `border.rounding` / `border.smoothing` — grounded, but "corner radius" NL
  would collide with `setRoundingScale`; one corner tool is enough.
- `session.commands.*`, `launcher.actions`, `launcher.enableDangerousActions` —
  command strings / dangerous-by-name: out of safety scope by construction.
- `notifs.*` — the on/off *toggle* stays excluded ("no single 'notifications
  enabled' boolean exists", [C18], §2.7) — the §3.6 notifications on/off
  dead-end and the §2.7 `toggleNotifications` row reflect that. Two count
  keys with complete grounding and unambiguous noun surfaces are included
  instead — `notifs.maxPopups` (stepper 0–30 + live reader,
  `NotificationPreferencesPage.qml:137-145`, `Content.qml:85`, [C32]) and
  `notifs.maxNotifs` (stepper 20–2000 + live reader, `:147-156`,
  `Notifs.qml:27`, [C32]) — tools 16/17 above. The other notifs keys stay
  out; §16 has the specific reasons.

---

## 2. Honest mapping of #120's example tools

| #120 asks for | This design | Why |
|---|---|---|
| `setBarHeight` | `setBarScale` | This port has **scale, not pixel bar height** — `BarWrapper.qml:24-26`: `contentWidth = innerWidth * barScale` ([C12]). "Thinner/taller bar" = lower/higher `bar.scale`. |
| `setDockPosition` | **not a tool** → AMBIGUOUS verdict | No independent dock left/right key exists. The dock is a bar *element*: its placement is the `zone` of the `dock` entry inside `bar.entries` (a list of objects, `barconfig.hpp:291-315`), which the leaf-writer deliberately does not touch. The parser answers with a clarifying question: "the dock's left/right placement is set in Nexus → Panels → Taskbar → Elements; did you mean to move the **whole bar** (`move the bar to the left`)?" — it never silently moves the whole bar when the user said "dock". |
| `setCornerRadius` | `setRoundingScale` | Corner rounding is **token-scaled, not pixels**: `appearanceconfig.cpp:32-33` — `extraSmall() = tokens->extraSmall() * m_scale`. `border.rounding` (px) exists but is deliberately not a tool (§1.3). |
| `enableBlur` / `disableBlur` | `setBlurEnabled` | Direct map. Blur in shell.json is **on/off only** — there is no blur-strength key; "increase the blur" therefore parses to `true` with an explicit note (§3.5). |
| `setAnimationSpeed` | `setAnimationSpeed` with **semantic inversion** | It scales *durations* (`AnimatedPasswordMask.qml:116` etc., [C26]): lower = faster. The parser maps "faster" → step DOWN, "slower" → step UP; absolute "animation speed 0.5" is interpreted as the **scale value** (the upstream UI's own presentation, "Animation speed scale" `AppearancePage.qml:319`), with the inversion stated in every plan note for this tool. |
| `setAccentColor` | **NOT shell.json** → SUGGESTED verdict | Accent color lives in the scheme system behind `caelestia scheme set -n <name>` (state in `$XDG_STATE_HOME/caelestia/scheme.json`, `caelestia-color` header + usage, [C25]). Emitted ONLY as an inert `SUGGESTED_NOT_EXECUTED:` string, exactly like every existing layer's command suggestions (`engine.py:50`, [C24]). |
| `setWallpaper` | **NOT shell.json** → SUGGESTED verdict | Same system: `caelestia wallpaper -f <path>` ([C25]); inert string only. |
| `toggleNotifications` | **deliberately unmapped** → NO_INTENT verdict with note | `notifsconfig.hpp` has no `enabled` boolean ([C18]); the closest knobs (`maxPopups`, `maxNotifs`, `expire`) are not "notifications on/off". The parser says so honestly instead of faking a toggle. |

### 2.1 #120's five example sentences → parser outcomes (traceability table)

| sentence (issue #120, verbatim) | verdict | ops / content |
|---|---|---|
| "Make my bar thinner." | `INTENT` | `setBarScale` step −0.1 (e.g. 1.0 → 0.9; clamped at 0.6 if already low) |
| "Move the dock to the left." | `AMBIGUOUS` | dock-position explanatory dead-end (§3.6): dock placement = `bar.entries` zones, not a registry key; offers `setBarPosition("left")` for the whole bar via clarifying question; writes nothing |
| "Increase the blur." | `INTENT` | `setBlurEnabled` = true, note: "blur in shell.json is on/off; there is no strength knob to increase" |
| "Make everything feel more compact." | `INTENT` | preset `compact` = 3-entry plan (§3.7); dry-run lists all entries; `--apply` gate required |
| "Give the desktop a minimal look." | `INTENT` | preset `minimal` = 4-entry plan (§3.7) |

---

## 3. Intent parser grammar (`parser.py`)

Deterministic, stdlib `re` only, **a pure function**: `parse(text) -> dict`.
No file I/O, no environment, no clock, no randomness — identical input always
produces an identical result (same guarantee as Layer 1's engine docstring,
`engine.py:4-9`). Value resolution (reading current values, clamping) happens
only in the planner.

### 3.1 The op model

```json
{"tool": "setBarScale", "action": "set"|"multiply"|"step", "value": <number|bool|string>, "raw": "<matched text>"}
```

- `set` — absolute: from a plain number ("1.2", "to 1.5"), an enum word
  ("left"), or bool wording (enable/disable).
- `multiply` — relative percentage: `value` is the factor (e.g. "20% bigger" →
  `1.2`; "20% smaller" → `0.8`).
- `step` — direction without magnitude: `value` is the signed step count,
  always ±1 ("thinner" → −1). "a bit / slightly" does NOT change the step
  count (still ±1) — documented, deterministic.

### 3.2 Verdict model (mirrors Layer 1's posture, [C24])

`parse()` returns:

```json
{"verdict": "INTENT"|"AMBIGUOUS"|"NO_INTENT"|"SUGGESTED",
 "ops": [...],            // INTENT only
 "candidates": [...],     // AMBIGUOUS: tool names + one-line description
 "question": "...",       // AMBIGUOUS/NO_INTENT: the clarifying question
 "notes": [...],          // honest caveats (bool-no-strength, inversion, ...)
 "suggestions": [...]}    // SUGGESTED only: inert command strings
```

- **AMBIGUOUS** — target cannot be resolved ("make it smaller"): list the
  candidate tools and ask a clarifying question. Never silently pick one
  (Layer 1's rule, `engine.py:380-381`).
- **NO_INTENT** — nothing matched: the honest answer plus the full list of
  supported settings (`--list-tools` equivalent) and pointers to Nexus and to
  the four troubleshooting layers. Mirrors Layer 1's NO_MATCH posture
  (`engine.py:382-383`).
- **SUGGESTED** — recognized request outside shell.json (accent/wallpaper):
  inert strings only, prefixed `SUGGESTED_NOT_EXECUTED:` ([C24]).

### 3.3 Matching algorithm (fixed precedence, no scoring, no ML)

1. **Normalize**: lowercase; collapse runs of whitespace to one space; strip
   surrounding quotes and trailing `.,!?`. Keep `%`, `.`, `-` (decimals and
   negatives must survive).
2. **Preset check** (§3.7) — before anything else, so "compact" is never
   consumed by per-tool synonyms.
3. **Scheme/wallpaper detection** (§3.6) — nouns `accent`, `accent color`,
   `color scheme`, `scheme`, `palette`, `theme colors` → SUGGESTED
   (`caelestia scheme list` / `caelestia scheme set -n <name>`);
   `wallpaper`, `background image`, `desktop background` → SUGGESTED
   (`caelestia wallpaper -f <path>`, `-r` for random). The assistant never
   parses the color name or file path — it cannot validate them; the suggestion
   carries a placeholder and the `list` pointer ([C25]).
4. **Explanatory dead-ends** (§3.6) — dock+position, notifications toggle,
   transparency on/off, font family: verdict + honest note, no ops.
5. **Per-tool noun match**: a tool matches when one of its `nouns` regexes
   appears AND a cue of an applicable class appears (position word for the
   enum tool; number/size-direction for numeric tools; enable/disable wording
   for bool tools; more/less-transparent for the transparency tool).
6. If exactly one value phrase (number, percent, or direction) exists in the
   sentence, it applies to **all** noun-matched tools ("make the bar and the
   dock icons bigger" → two step ops). If **multiple distinct value phrases**
   exist ("bar scale 1.2 and blur on") → AMBIGUOUS: "split that into separate
   requests".
7. Noun matched but no applicable cue ("the dock", "blur") → the tool is a
   candidate-without-value; if nothing else matched fully → AMBIGUOUS asking
   what to do with it.
8. No noun matched but a size direction word present ("make it smaller") →
   AMBIGUOUS with the fixed candidate list (all numeric tools whose direction
   vocabulary matched), in registry order.
9. Nothing matched at all → NO_INTENT.

### 3.4 Number extraction and relative semantics

Regexes (compiled once, module level):

```
NUM := -?\d+(?:\.\d+)?
PCT := (\d+(?:\.\d+)?)\s*%
```

- Plain number, optionally after `to`/`at`/`of` ("set the bar scale to 1.4",
  "bar scale 1.4") → `action: "set"`, `value: <float>`.
- `N%` **with** a comparative word (bigger/smaller/increase/decrease/…) →
  `action: "multiply"`, `value: 1 ± N/100` (sign from the word). Applied by the
  planner as `new = old * value`, then clamped (§4.4).
- `N%` **without** a comparative word:
  - on `setTransparencyBase` (the one tool whose own UI displays percent,
    `AppearancePage.qml:143`) → absolute `set` of `N/100`;
  - on any other tool → AMBIGUOUS: "percent of what? say e.g. '20% bigger',
    or give a plain number like 1.2".
- Direction word without a number → `action: "step"`, `value: ±1` (§1.2 step
  per tool; the planner clamps).
- Bool tools accept **only** enable/disable wording; any number or percent on a
  bool tool → REJECTED entry (`"this setting is on/off only; it has no
  magnitude"`), never a coerced value.
- "reset"/"default" + tool noun → `action: "set"`, `value = registry default`.

Direction vocabularies (per class; case-insensitive):

- **down/decrease**: `thinner|smaller|slimmer|shrink|reduce|decrease|less|
  lower|down|tighter|denser` (sizes); `faster|quicker|snappier` (animation);
  `more transparent|see-through|lighter` (transparency base).
- **up/increase**: `thicker|bigger|larger|wider|grow|increase|more|raise|up|
  roomier|spacious` (sizes); `slower|smoother` (animation); `more opaque|
  more solid|less transparent` (transparency base).
- **bool on**: `enable|turn on|switch on|show|on`; **bool off**:
  `disable|turn off|switch off|hide|off`. Comparative words on bools map to
  on/off ("increase the blur" → on, "less blur" → off) with the no-magnitude
  note (§3.5).
- **position**: `top|bottom|left|right` (+ "edge", "side" tolerated adjacent).

Per-tool noun lists (registry `nouns`, regex alternations):

- `setBarScale`: `bar|taskbar|panel` (combined with a size cue)
- `setBarPosition`: `bar|taskbar|panel` (combined with a position cue)
- `setDockIconSize`: `dock|dock icons|taskbar dock`
- `setBarPersistent`: `bar|taskbar` + `persistent|always visible|auto.?hide`
- `setLivePreviews`: `live previews|window previews|thumbnails|previews`
- `setBlurEnabled`: `blur|background blur|frosted glass`
- `setTransparencyBase`: `transparency|opacity|base opacity`
- `setRoundingScale`: `rounding|corner radius|corners|corner rounding`
- `setSpacingScale`: `spacing|gaps|gap`
- `setPaddingScale`: `padding|insets`
- `setFontScale`: `font|text|text size|font size|fonts` (size cue required —
  "font family/name/typeface" hits the dead-end in §3.6)
- `setAnimationSpeed`: `animations?|animation speed|transitions|motion|
  effects speed`
- `setBorderThickness`: `border|shell border|outline` (size cue; "remove the
  border"/"borderless" → absolute 0)
- `setLauncherMaxShown`: `launcher|search results|launcher results`
- `setPitchBlack`: `pitch black|bezel mode|bezel`; the bare phrase
  "pitch black" is ALSO an implicit bool-on cue when the sentence carries no
  other value phrase — "make the shell pitch black" → `setPitchBlack true`
  (the mirror of the "borderless" → 0 rule; with an explicit on/off word,
  comparative, number, percent or reset present, the standard §3.4/§3.5
  paths apply instead)
- `setNotifsMaxPopups`: `notification popups|popup notifications`
- `setNotifsMaxNotifs`: `stored notifications|max stored notifications`
- `setDockBadges`: `app badges|badges|badge` (the shipped control's own
  label; see §16 for why the bare "dock" word is deliberately NOT in the
  noun surface)

The conflict rule when one noun feeds two tools (`bar` + a size cue vs `bar` +
a position cue): the cue class disambiguates — a sentence containing both a
position word and a size word with the `bar` noun is AMBIGUOUS.

### 3.5 Bool semantics

Bool tools accept only enable/disable wording, never numbers (a number on a
bool tool is a REJECTED entry, not a coercion). Because upstream blur is
strictly boolean while #120's example says "Increase the blur", comparative
words on bool tools map to on/off **with an honest note attached to the op**:
`"blur in shell.json is on/off only — there is no strength to increase;
enabling it"`. The same note shape is used for `livePreviews`.

### 3.6 Explanatory dead-ends (deterministic special cases)

Each is a fixed (pattern → verdict, note) rule, evaluated at precedence 3–4:

- `dock` noun + position word → AMBIGUOUS: dock left/right placement is
  `bar.entries` zones (Nexus → Panels → Taskbar → Elements), not a registry
  key; clarifying question offers `move the bar to the left`
  (`setBarPosition`) if the whole bar was meant. (#120 sentence 2 lands
  here.)
- `notifications?` + on/off wording → NO_INTENT with note: no upstream
  "notifications enabled" boolean exists in `notifsconfig.hpp` ([C18]); the
  clarifying question points at the count tools instead —
  `notifs.maxPopups` / `notifs.maxNotifs` (§1 rows 16/17) — "set the max
  notification popups to 5".
- `transparency` + on/off wording → NO_INTENT with note:
  `appearance.transparency.enabled` exists upstream
  (`appearanceconfig.hpp:215`) but is deliberately not a tool (§16), and
  turning transparency off has upstream UI side effects (disables blur,
  `AppearancePage.qml:132-136`); the level tool (`setTransparencyBase`) is
  offered instead in the question.
- `font family|font name|typeface` → NO_INTENT with note: only the *size*
  scale is a tool; family lives in `appearance.font.*.family` (string trees,
  out of scope).
- accent/scheme/palette/wallpaper → SUGGESTED (§3.3 step 3).

### 3.7 Presets

- **`compact`** — trigger: `compact|more compact|denser|tighter`. Values:
  `bar.scale = 0.85`, `appearance.spacing.scale = 0.9`,
  `appearance.padding.scale = 0.9`.
- **`minimal`** — trigger: `minimal|minimalist|minimal look|cleaner look|
  simpler look`. Values: `bar.scale = 0.8`, `appearance.spacing.scale = 0.9`,
  `appearance.padding.scale = 0.9`, `appearance.rounding.scale = 0.9`.

Both expand to a multi-entry plan of ordinary `set` ops (all values in range).
A multi-setting plan prints **the full list** and — like every plan — requires
the explicit `--apply` gate; that is the CLI equivalent of #120's
"confirmation for larger changes" (§7c). The preset note states the values are
conservative defaults, not an upstream-defined look.

---

## 4. Planner (`planner.py`)

Input: `ops` from the parser + target file path. Output: a **plan**:

```json
{"verdict": "INTENT", "file": "<path>", "entries": [
   {"tool": "setBarScale", "path": "bar.scale", "action": "step",
    "old": 1.0, "new": 0.9, "clamped": false, "no_op": false,
    "note": "step thinner (-0.1)"},
   {"tool": "setAnimationSpeed", "path": "appearance.anim.durations.scale",
    "action": "set", "old": 1, "new": 0.5, "clamped": false, "no_op": false,
    "note": "durations scale: lower = faster"}],
 "notes": [...], "errors": []}
```

### 4.1 Reading the current state

- File missing → parse as `{}`; every `old` = registry default; plan note
  `"target file does not exist; defaults assumed (file will be created on
  apply)"`.
- File exists but `json.loads` fails → **abort the whole run**: print error to
  stderr, exit 1, file untouched (#120: not applied — and the running shell's
  own loader would retry-and-toast on it too, [C10]).
- Top-level not a JSON object → abort identically (shell.json is an object
  tree; the loader would quarantine a non-object, `objectnode.cpp:79-84`).
- Deep-copy the parsed object; the plan holds plain values only.

### 4.2 Resolving a leaf

Walk the dotted path segment by segment. Missing intermediate objects →
`old = default` (note: `"key was absent; default assumed"`). An intermediate
segment exists but is not an object (e.g. `"bar"` is a string) → **abort that
entry with a TYPE_MISMATCH error** — no silent coercion, no structural repair.

### 4.3 Type checking

- `float`/`int` tools: existing value must be a JSON number (`int` or `float`
  in Python terms; `32.0` is acceptable for an int-typed key — JSON has one
  number type and upstream's qreal/int codecs decode both).
- `bool` tools: existing value must be JSON `true`/`false`. **A JSON number is
  NOT an acceptable bool** — Python's `json` parses `1` to `int`, and
  `1 == True`, so the implementation must check `type(v) is bool` explicitly.
- `enum` tool: existing value must be a string.
- Any disagreement → abort that entry with TYPE_MISMATCH (plan-level: see 4.5).

### 4.4 Computing `new`

- `set`: validate against range/enum. **Absolute out-of-range → REJECTED**
  entry with the allowed range in the error (per #120: "it simply isn't
  applied"). Bool values come only from the parser's enable/disable mapping.
- `multiply`: `new = old * factor`; then **clamp** to range; if clamped, set
  `clamped: true` and add note `"clamped to <min/max>"`.
- `step`: `new = old ± step`; clamp identically.
- Rounding (deterministic): float tools → `round(new, 2)` (Python's
  round-half-even is accepted and deterministic); int tools →
  `int(new + 0.5)` for non-negative values (all int-tool ranges are positive;
  avoids Python's banker's rounding on `.5`).
- `new == old` → `no_op: true` (entry still listed; apply skips it).

### 4.5 All-or-nothing semantics

If **any** entry carries an error (REJECTED or TYPE_MISMATCH), the plan is
marked `"apply_blocked": true`. `--apply` then refuses to write anything and
exits 1 (§5.2). Clamped and no-op entries never block. This makes multi-entry
plans atomic from the user's point of view.

### 4.6 Monitor-override warning (read-only, best-effort)

For each non-`global_only` entry, list `<configDir>/caelestia/monitors/*/
shell.json`; for each that parses as JSON and contains the entry's dotted path,
add a note: `"screen '<name>' has a per-monitor override for this key; the
global change will be shadowed there"`. Unparseable/unreadable monitor files
are skipped silently (they are not ours to judge). `global_only` tools skip
this check — the loader quarantines global-only keys in overlay files anyway
(`objectnode.cpp:144-147`, [C23]). **No monitor file is ever written.**

---

## 5. Applier + safety protocol (`applier.py` — the ONLY module that writes)

### 5.1 CLI surface

```
python3 -m assistant.settings "make the bar thinner"                 # dry-run (DEFAULT)
python3 -m assistant.settings "make the bar thinner" --apply         # write (gated)
python3 -m assistant.settings "..." --file PATH                      # target override (tests)
python3 -m assistant.settings "..." --json                           # machine-readable plan
python3 -m assistant.settings --list-tools [--group NAME]            # registry table (§11)
python3 -m assistant.settings --tool NAME                            # one tool's full spec (§11)
python3 -m assistant.settings --call setX=value [--call ...] [--apply]  # direct tool calls (§11)
python3 -m assistant.settings --explain "..."                        # read-only, never writes (§13)
python3 -m assistant.settings --history                              # bounded undo log (§14)
python3 -m assistant.settings --undo N / --undo-id ID                # undo by count or id (§14)
python3 -m assistant.settings --list-presets                         # named preset bundles (§15)
python3 -m assistant.settings --preset NAME --apply [--confirm]      # apply a preset (§15)
python3 -m assistant.settings --restore [--file PATH]                # one-level undo of the last apply
```

- Default target: `$XDG_CONFIG_HOME/caelestia/shell.json`, falling back to
  `$HOME/.config/caelestia/shell.json` — matching
  `QStandardPaths::GenericConfigLocation` ([C7]) and the same two env vars
  Layer 1 already allowlists (`engine.py:48`, [C29]). Never any other path
  unless `--file` says so.
- `--apply` and `--restore` are mutually exclusive; the registry/query flags
  (`--list-tools`, `--tool`, `--explain`, `--history`, `--list-presets`)
  ignore TEXT; TEXT is required otherwise (argparse handles all of this;
  exit 2 on usage errors, Python's default).
- Exit codes: **0** = verdict printed / applied / restored / listed (including
  AMBIGUOUS, NO_INTENT, and dry-run plans containing REJECTED entries — an
  honest answer is a successful run); **1** = operational failure: target file
  invalid JSON / non-object, unreadable file, `--apply` with an
  `apply_blocked` plan (nothing written), write failure, `--restore` with no
  backup.

### 5.2 Dry-run default

Without `--apply`: print the plan (or verdict) and **write nothing** — not the
target, not a backup, not a tmp file — exit 0. The printed plan ends with the
exact re-run command including `--apply`, so the confirmation step is a
copy-paste, verifiable in shell history. This is the CLI equivalent of #120's
"confirmation for larger changes" (§7c).

### 5.3 Write protocol (`--apply`, plan not blocked)

1. If every entry is `no_op`: print "no changes needed", write nothing, exit 0
   (no pointless backup churn).
2. **Backup**: if the target file exists, copy its current bytes to
   `<file>.assistant-backup` (single slot — an existing backup is overwritten;
   this is one level of undo, §7e). If the target does **not** exist, write a
   **zero-byte** `<file>.assistant-backup` marker. (Sound because the planner
   aborts on any existing-but-invalid file, so a zero-byte backup can only ever
   mean "there was no file".)
3. **Serialize**: take the planner's deep-copied object, set only the
   whitelisted registry leaf paths (creating intermediate dicts along registry
   paths only), then `json.dumps(data, indent=4) + "\n"`. Every other key is
   preserved in spirit: values are never altered, removed or reordered (Python
   dicts keep insertion order). 4-space indent matches
   `QJsonDocument::toJson()`'s Indented style that the shell itself writes
   (`settingsfile.cpp:168`, [C11]) — **cosmetic only**: the shell reloads by
   parsing, and its own saves are sparse anyway (`objectnode.hpp:20`,
   `toJson(bool sparse = true)`), so byte-style is not a contract. Unknown keys
   the shell would quarantine survive the merge untouched (and survive the
   shell's own round-trip, `objectnode.cpp:70-71`, [C23]).
4. **Atomic replace**: write the serialized text to `<file>.assistant-tmp`
   (utf-8), then `os.replace(tmp, file)` — POSIX `rename(2)`, atomic. No
   fsync by design (the rename is the visibility boundary; the shell's watcher
   tolerates transient states, [C10]). `os.replace` is **not** in the lint's
   `FORBIDDEN_OS_ATTRS` (`schema_lint.py:52`, [C21]) — verified.
5. On any exception: best-effort unlink of the tmp file, leave target and
   backup untouched, exit 1.
6. **Never touch any other file for a plain apply.** The only paths ever
   opened for writing by an apply/restore are the target,
   `<target>.assistant-backup`, `<target>.assistant-tmp`, and — on a
   successful apply only — an entry appended to the bounded undo-history
   file (§14); nothing else in the filesystem is ever touched.

Symlink handling: if the target path is a symlink, resolve it with
`os.path.realpath` and operate on the resolved path (backup/tmp siblings of the
*resolved* file), so the rename replaces the real file rather than detaching
the link.

### 5.4 Restore (`--restore`)

- Requires `<file>.assistant-backup` to exist, else exit 1 with "no backup to
  restore".
- Zero-byte backup → **delete** the target file (restores the "no file" state).
- Otherwise `os.replace(backup, file)` — atomic, and the single slot is
  **consumed** (a second `--restore` fails with "no backup"; a new `--apply`
  refreshes the slot). One level of undo, documented.

### 5.5 Rendering (text mode; `--json` emits the same structure)

Header mirrors the existing layers' honesty banner (`engine.py:468-469`):

```
caelestia assistant — settings layer (NL -> validated tool calls; dry-run by default)
Nothing is written without --apply; this run writes nothing.        [dry-run]

Verdict: INTENT — 2 changes planned on ~/.config/caelestia/shell.json
  1. bar.scale: 1.0 -> 0.9            (setBarScale, step thinner)
     note: clamped to range 0.6-1.6
  2. appearance.blur: false -> true    (setBlurEnabled)
     note: blur in shell.json is on/off only; there is no strength to increase

Apply with: python3 -m assistant.settings "make the bar thinner and increase the blur" --apply
```

AMBIGUOUS mirrors Layer 1's wording ("Verdict: AMBIGUOUS — several settings
fit; name one:" + numbered candidates + the clarifying question). NO_INTENT
mirrors "Verdict: NO supported setting matched." + the honest list of supported
settings. SUGGESTED prints inert lines prefixed `SUGGESTED_NOT_EXECUTED:`.

### 5.6 Module layout

```
assistant/settings/
    __init__.py       # thin docstring (like the other layers) — no exports
    registry.py        # ToolSpec + the frozen 18-tool table (§1) + lookup helpers
    parser.py          # parse(text) — pure (§3)
    planner.py         # plan(ops, file) — reads the target file, validates (§4)
    applier.py         # apply/restore — the ONLY writing code (§5)
    explain.py         # --explain: read-only "why does it look like this" (§13)
    history.py         # bounded 12-entry undo log (§14)
    presets.py         # named preset bundles + the confirmation gate (§15)
    curations.py        # the merge/exclusion rules the registry generator applies (§10)
    enumerate.py        # walks the C++ config headers into a leaf-key table (§10)
    ui_ranges_data.py   # the 318-row Nexus-control transcription (§10)
    build_registry.py   # joins enumerate.py + ui_ranges_data.py + curations.py -> tools.json (§10)
    tools.json           # the generated 277-tool registry, embedded into SettingsTools.qml (§10, §12)
    cli.py              # argparse, rendering, exit codes
    __main__.py         # shim: from .cli import main; SystemExit(main())
    DESIGN.md           # this file
    tests/
        __init__.py
        test_registry.py    # citations + generated-registry drift guards (§9, §10)
        test_parser.py
        test_planner.py
        test_applier.py
        test_explain.py     # §13
        test_history.py     # §14
        test_presets.py     # §15
        test_cli_calls.py   # --call/--tool/--group direct addressing (§11)
        test_qml_service.py # byte-identity + static checks on SettingsTools.qml (§12)
        test_safety.py      # additional applier/registry safety regressions
```

---

## 6. Safety posture (same as the existing layers)

- **Imports**: stdlib only, and only names already in `ALLOWED_IMPORTS.txt`
  ([C22]): `json`, `re`, `os`, `sys`, `pathlib`, `argparse`, `typing`,
  `dataclasses` — plus optionally `glob` (monitor scan, §4.6) and `math`-free
  int rounding (`int(x + 0.5)`; no `math` needed). No allow-list entry beyond
  those is required by anything in this module, including the generated
  registry pipeline (§10) and the undo history (§14).
- **No subprocess, no `os.system`** — `FORBIDDEN_IMPORTS` and
  `FORBIDDEN_OS_ATTRS` cover the module automatically
  (`schema_lint.py:33-52`, [C21]); the module simply never imports or calls
  them.
- **No network at all** in this module (unlike Layer 3, not even loopback).
- **No execution of suggested commands**: scheme/wallpaper suggestions stay
  inert strings with the `SUGGESTED_NOT_EXECUTED:` prefix ([C24]).
- **Write scope**: exactly one target file plus three siblings — the
  transient tmp, the single-slot backup, and the bounded undo-history file
  (§14) — only behind `--apply`, atomic rename.
- **Lint coverage is automatic**: `check_import_policy` scans
  `assistant/**/*.py` via `root.rglob("*.py")` from the assistant root
  (`schema_lint.py:123-125`, [C21]) — every file in this module, including
  the generated-registry pipeline, is covered without a lint change; the
  existing `selfcheck` and `test_safety_lint` extend to it for free.
- **Parser purity**: `parse()` performs no I/O, so no input string can ever
  cause a file access, let alone a write, before the planner/applier stages.

---

## 7. Alternatives considered

**(a) Writing shell.json vs suggesting manual edits vs in-shell IPC.**
Suggesting manual edits only ("edit `bar.scale` yourself") would reproduce the
status quo of Layers 1–4 and not implement #120's feature at all. An in-shell
IPC/config-manager API is the *ideal* end state #120 sketches, but it does not
exist today (shell.qml registers exactly `region` and `lock`, [C19]) and
building it means modifying the C++/QML shell — deliberately left to the
maintainer (§12 describes the native-QML alternative this module does ship).
The watched-file route is the only real external entry
into the live config system, and it *is* "through the existing configuration
system": the shell's own SettingsFile reloads the file ([C10]), the loader
re-validates every key against the runtime schema and quarantines unknown or
ill-typed ones ([C23]), and the live update happens inside the shell. The
assistant's own validation (registry ranges) is deliberately stricter, so the
shell's quarantine should never trigger on assistant output in practice.

**(b) Deterministic regex parser vs local Ollama intent parsing.**
The repo already ships optional loopback Ollama for Layer 3 *suggestions*;
using it to *parse intents that get applied to config* would make writes
depend on a model's output — unreproducible, untestable in CI, unavailable
offline, and at odds with this repository's no-training posture and the
existing determinism guarantees (`engine.py:6-9`). The grammar in §3 covers
#120's scope ("simple NL requests") with zero ML; Ollama-based parsing can be
layered later behind the same op model without changing the planner/applier.

**(c) Dry-run default vs interactive confirmation prompt.**
#120 asks for "confirmation for larger changes". An interactive y/n prompt is
untestable in the repo's shell-based test harness, behaves differently under
piped stdin, and cannot be audited after the fact. A dry-run default with an
explicit `--apply` gate is the CLI equivalent: the printed plan IS the
confirmation, the re-run command is the "yes", and shell history records it.
Multi-setting changes are not treated specially — every write is gated, which
is strictly safer.

**(d) Reject vs clamp for out-of-range values.**
Absolute requests ("set bar scale to 5") state an explicit intent; silently
changing it to 1.6 would write something the user never asked for — REJECT, per
#120's "it simply isn't applied". Relative requests ("thinner", "20% smaller")
carry a *direction*, not a target; refusing to move at all because the result
would cross a boundary would be pedantry — CLAMP with a visible "clamped"
notice in the plan. Both behaviors are deterministic and surfaced in the plan.

**(e) Single-slot backup vs full history.**
A timestamped history (N backups) creates unbounded files in the user's config
directory — exactly the kind of side effect this design's posture forbids —
and #120 needs only "undo": one level per apply, plus (§14) a bounded log of
recent applies for visibility. `<file>.assistant-backup` is a single,
documented, discoverable slot; `--restore` consumes it atomically.

---

## 8. Non-goals

- **Per-screen overrides** (`~/.config/caelestia/monitors/<screen>/shell.json`):
  never written; only the read-only shadow warning of §4.6.
- **Unbounded undo history** — §14 adds a bounded 12-entry log plus the
  single-slot `--restore`; a fully unbounded, never-pruned log stays a
  non-goal (unbounded files in the user's config directory, per (e) above).
- **Redo** — deliberately not offered alongside undo (§14).
- **Nexus/QML integration beyond the one deliberate touchpoint** — §12
  documents `shell/services/SettingsTools.qml`, the sole exception; no other
  C++/QML file is touched.
- **Accent color & wallpaper application** — scheme-system territory; inert
  suggestions only (§2).
- **Notification toggling** — no upstream boolean ([C18]); honest NO_INTENT.
- **The in-shell ConfigManager/tool-calling API itself**, as #120 originally
  sketches a C++-side implementation — left to the maintainer; §12's QML
  service is this module's own answer to the same need, built without
  touching the C++ shell.
- Additional knobs deliberately not tools: `appearance.transparency.enabled`,
  `border.rounding`, `border.smoothing`, `bar.workspaces.shown` (§1.3), and
  the wider set catalogued in §16, plus any list-typed or command-typed key
  and any string family/name key.

---

## 9. Test plan (run via
`PYTHONPATH=. python3 -m unittest discover -s assistant/settings/tests`;
wired as a fifth suite in `tests/test_assistant.sh`)

**Parser cases**
- #120's five sentences → the exact verdicts/ops of §2.1.
- Absolute in/out of range: "set the bar scale to 1.4" (op set 1.4) / "to 5"
  (REJECTED) / "to 0.3" (REJECTED).
- Relative: "make the bar 20% smaller" → multiply 0.8; "thinner" → step −1;
  clamping asserted at the planner with a fixture file.
- Percent without direction on a scale tool → AMBIGUOUS; on transparency →
  absolute N/100.
- Bool from number: "blur 50%" → REJECTED ("on/off only").
- Inversions: "make animations faster" → durations.scale DOWN; "slower" → UP;
  "more transparent" → base DOWN; "more opaque" → UP.
- Targetless "make it smaller" → AMBIGUOUS with the fixed candidate list.
- "change my keyboard layout" → NO_INTENT listing supported settings.
- "set the accent color to red" / "new wallpaper" → SUGGESTED, inert strings,
  `SUGGESTED_NOT_EXECUTED:` prefix present.
- Multi-tool sentence ("make the bar and the dock icons bigger") → two ops;
  mixed value shapes → AMBIGUOUS.
- Purity: `parse()` must not open files (audit `parse` source for `open(`/`os.`
  in the test, or run it with `open` monkeypatched to raise).

**Planner/applier safety regressions**
- Dry-run default: with a fixture file, no byte changes to the target, no
  `.assistant-backup`, no `.assistant-tmp` after the run.
- `--apply`: only the target changes; backup exists and equals the pre-apply
  bytes; no tmp file remains.
- Invalid JSON target (dry-run and apply) → exit 1, file untouched.
- Top-level non-object target → exit 1.
- Type mismatch (`"bar": "oops"` or `bar.scale` as string/bool) → entry error,
  apply_blocked, nothing written.
- Absolute out-of-range with `--apply` → nothing written, exit 1.
- Relative clamp: fixture `bar.scale: 0.65`, "bar 20% smaller" → 0.6 +
  clamped note.
- Backup/restore round-trip: apply → mutate → `--restore` → byte-identical to
  pre-apply; second `--restore` → exit 1; zero-byte marker case: apply onto a
  missing file → `--restore` deletes the file again.
- No-op plan ("set bar scale to 1.0" when it is 1.0) → "no changes needed",
  nothing written, no backup.
- Monitor shadow warning: fixture `monitors/DP-1/shell.json` containing
  `bar.position` → note present for `setBarPosition`, absent for global-only
  tools.
- Symlinked target: write lands on the resolved file, link stays attached.

**Registry grounding (drift guard)**
- `test_registry.py` re-verifies every citation by grepping the real C++
  headers from the repo root (`shell/plugin/src/Caelestia/Config/*.hpp`): each
  tool's `CONFIG_PROPERTY(...)` line must exist with the declared type/name
  (e.g. `rg -n 'CONFIG_PROPERTY\(qreal, scale, 1.0\)' barconfig.hpp`). If the
  repo layout is absent (module copied elsewhere), the test **skips with a
  loud message** (`self.skipTest("repo sources not present; citation
  re-verification skipped")`), never silently passes.

**Safety lint** — no new test needed: `check_import_policy` rglobs
`assistant/**/*.py` ([C21]) and the existing `test_safety_lint` covers the new
module automatically once the files exist.

**Further coverage** — the registry-generation drift guards, direct-call
addressing, QML cross-checks, explainability, undo history and presets each
have their own test classes, described alongside the feature in §10-§15.

---

## 16. Registry scope: what's included and why

The registry was built by re-enumerating the whole `shell.json` schema from
`Config/rootnodes.hpp` — every `CONFIG_SUBOBJECT` root and every config
header it includes, every `CONFIG_PROPERTY` / `CONFIG_GLOBAL_PROPERTY` /
`CONFIG_ENUM_PROPERTY` leaf with its type and default — and evaluating each
simple-scalar leaf against five criteria: (a) key path + type is pinned at
its C++ declaration line, (b) its range or enum is grounded in a shipped
Nexus control or a C++ clamp — never invented, (c) it has an unambiguous
noun surface that collides with no existing tool noun and no dead-end
pattern, (d) it is not a SAFETY exclusion (§1.3 — command/dangerous keys,
never revisable), (e) a single-key write cannot create a broken or
surprising state (no coupled key, no master-switch gate, no runtime process
that re-syncs it). A leaf failing any one criterion is not a tool; nothing
in the registry was guessed.

The frozen 18-tool natural-language surface (§1) covers the tools where
that evaluation was clean from the start. Four of the eighteen —
`setPitchBlack` (`appearance.pitchBlack`, [C31]), `setNotifsMaxPopups` /
`setNotifsMaxNotifs` (`notifs.maxPopups`/`maxNotifs`, [C32]) and
`setDockBadges` (`bar.dock.showBadges`, [C36]) — were added to that surface
once the wider schema walk reached them, under the identical five-criteria
bar; each is fully cited in §1's table and the appendix, and none needed a
range invented — 0–30, 20–2000 and the rest are the shipped steppers' own
bounds. `setDockBadges` is the one case worth a note: its bare noun surface
("app badges"/"badges"/"badge") collides with nothing in the schema, but
the *tool* it sits next to, `setDockIconSize`, shares the bare word "dock".
Traced through the parser: an on/off phrase with a volunteered "dock"
("hide the dock badges") applies a bool op only to the bool-kind tool, so
`setDockIconSize` receives no op and the plan is a clean single
`setDockBadges=false` — strictly better than the pre-existing behavior,
which was AMBIGUOUS. "Turn off badges on the dock" (two bool phrases) still
correctly split-AMBIGUOUS. A number sentence ("set the dock badges to 3")
correctly produces two REJECTED ops and a blocked apply. The one honestly
documented residual is a size comparative with a volunteered "dock" ("make
the dock badges bigger"), which also steps `iconSize` — the same
pre-existing bare-noun hazard the `previewScales` family below already has,
not a new one, and not fixable without changing the fixed matching
algorithm; it is pinned as a known-residual regression test.

Everything else the schema walk reached was evaluated and left out. Grouped
by the reason, not by when it was evaluated:

**Coupled state, not a safe single-key write.**
`appearance.transparency.enabled` ([C34]) — the upstream UI couples it to
`blur` (turning transparency off also disables blur and its toggle,
`AppearancePage.qml:132-136,226`) and needs a timing hack to re-sync blur
when re-enabled; whether a plain external write reaches the same visual
state as the UI's sequence can't be established from source, so it stays a
documented §3.6 dead-end, not a tool.

**Noun surface unavoidably collides.**
`bar.dragThreshold` and the equally-grounded sibling
`launcher`/`session`/`sidebar`/`dashboard`/`overview`/`utilities`
`.dragThreshold` keys ([C33]) — every natural phrasing must name the panel,
and every panel's bare noun already matches another tool (`bar` →
`setBarScale`, etc.), so the fixed noun-then-value matching algorithm would
silently misfire on both value and step phrasings. `bar.dock.recolourIcons`
and `bar.dock.currentDesktopOnly` — the first has no on/off word in the
§3.4 vocabulary at all ("recolor" isn't a bool cue), the second's noun is
shared by a second, unrelated key (`tabSwitch.currentDesktopOnly`) with its
own shipped toggle — a genuine two-key collision. `notifs.position` /
`monitor` / `fullscreen` — `position`'s seven values are hyphenated
compounds ("top-left"), which the single-word §3.4 vocabulary would scan as
two separate phrases, and "corner(s)" collides with `setRoundingScale`.

**Runtime-owned; an external write would be undone.**
`bar.workspaces.shown` ([C28]) — a KWin sync loop
(`BarWorkspaces.qml:34-51`) both writes it and creates/removes virtual
desktops to match; an external write would be half an operation and
overwritten on the next sync. `bar.workspaces.monitorCenter` and
`bar.dock.monitorCenter` ([C20]) — grounded declarations with no QML
consumer at all (only a code comment references the former).

**Display unit doesn't match the stored unit.**
`notifs.defaultExpireTimeout` / `notifs.fullscreenExpireTimeout` ([C35]) —
the shipped sliders display seconds while the keys store milliseconds
(`value: .../1000`, `onMoved: ... * 1000`); an honest tool would need a
per-tool unit transform the parser doesn't have, and guessing the unit is
exactly what the five-criteria bar forbids.

**Shadowed by an existing dead-end.**
`notifs.expire`, `notifs.actionOnClick`, `notifs.openExpanded` — every
natural on/off phrasing contains "notifications" + a bool word, which the
§3.6 notifications dead-end matches first by design; a noun avoiding it
would be unreachable. `notifs.clearThreshold` — its UI shows percent, but
the bare-percent rule is reserved for `setTransparencyBase` by name; a
second percent tool would change that documented semantic.

**Niche, kept out under the small-registry cap.**
`notifs.groupPreviewNum` / `expandThreshold` (steppers, grounded but
niche). `bar.previewScales.dock` / `previewFontScales.dock` and the rest of
the per-element preview/font-scale offsets — per-popout scaling knobs whose
noun ("dock", "font", "previews") collides with three different tools, and
which are inert no-ops unless a master switch the shipped UI itself flips
in pairs is separately on — failing both the noun and the safe-single-write
criteria. `bar.workspaces.perMonitor` (a per-bar bool, shipped toggle) and
the now-deprecated `perMonitorWorkspaces` (writing it is a half-migrated
write the loader ignores). `appearance.islands` — upstream's own UI labels
it "(Very Experimental)"; left to Nexus.

**List-, string- or command-typed; SAFETY exclusions, never revisable.**
`session.commands.*`, `launcher.actions`, `launcher.enableDangerousActions`
— command strings, dangerous by name. `border.rounding` /
`border.smoothing` — grounded, but "corner radius" would collide with
`setRoundingScale`. And the wide remaining catalog — `osd.*`, `lock.*`,
`general.*` (incl. the typed `timeouts`/`warnLevels` lists),
`services.*` (incl. `visualiserBars`, `maxVolume`/`audioIncrement`'s
percent-vs-fraction mismatch), `dashboard.*`, `background.*`, `nexus.*`,
`sidebar.*`, `utilities.*` (incl. the typed VPN-provider list),
`tabSwitch.*`, `audio.*`, `ai.*`, `paths.*` (credentials/endpoints, out of
scope by §0) — each entry is either string/list-typed, a percent-display
mismatch, a niche edge-geometry knob, or runtime-owned; none met all five
criteria with a clean noun surface.

---

## Appendix — Verified citations

Reproducible from the repo root; outputs are verbatim `rg`/`sed` output
against this checkout's `shell/plugin/src/Caelestia/Config/*.hpp` and the
cited QML files.

### [C1] bar leaf properties — `rg -n 'CONFIG_PROPERTY\(qreal, scale|CONFIG_PROPERTY\(bool, persistent|CONFIG_PROPERTY\(QString, position|CONFIG_PROPERTY\(bool, livePreviews|CONFIG_PROPERTY\(bool, monitorCenter|CONFIG_PROPERTY\(int, iconSize' shell/plugin/src/Caelestia/Config/barconfig.hpp`

```
44:    CONFIG_PROPERTY(bool, monitorCenter, false)
171:    CONFIG_PROPERTY(bool, monitorCenter, true)
174:    CONFIG_PROPERTY(int, iconSize, 32)
233:    CONFIG_PROPERTY(qreal, scale, 1.0)
243:    CONFIG_PROPERTY(bool, livePreviews, true)
246:    CONFIG_PROPERTY(bool, persistent, true)
262:    CONFIG_PROPERTY(QString, position, u"bottom"_s)
```

### [C2] BarDock node, livePreviews NVIDIA comment, position default — `sed -n '168,178p;239,246p;261,263p' shell/plugin/src/Caelestia/Config/barconfig.hpp`

```
class BarDock : public settings::ObjectNode {
    CONFIG_NODE(BarDock, settings::ObjectNode)

    CONFIG_PROPERTY(bool, monitorCenter, true)
    CONFIG_PROPERTY(bool, recolourIcons, false)
    CONFIG_PROPERTY(bool, showBadges, true)
    CONFIG_PROPERTY(int, iconSize, 32)
    CONFIG_PROPERTY(bool, currentDesktopOnly, false)
    CONFIG_PROPERTY(bool, previewOnDesktop, true)
    CONFIG_GLOBAL_PROPERTY(QStringList, pinnedApps, QStringList({ u"firefox"_s, u"org.kde.dolphin"_s }))
};
    // Live PipeWire window thumbnails (dock hover, overview, alt-tab, window info).
    // Disable if screen sharing / camera in other apps (e.g. Vesktop) freezes or
    // crashes - some NVIDIA + KWin setups can't handle KWin's screencast protocol
    // being used by two clients at once.
    CONFIG_PROPERTY(bool, livePreviews, true)
    CONFIG_SUBOBJECT(BarPreviewScales, previewScales)
    CONFIG_SUBOBJECT(BarPreviewFontScales, previewFontScales)
    CONFIG_PROPERTY(bool, persistent, true)
    CONFIG_PROPERTY(int, dragThreshold, 20)
    CONFIG_PROPERTY(QString, position, u"bottom"_s)
    CONFIG_SUBOBJECT(BarScrollActions, scrollActions)
```

### [C3] appearance properties — `rg -n 'CONFIG_PROPERTY\(qreal, scale, 1\)|CONFIG_GLOBAL_PROPERTY\(qreal, scale, 1\)|CONFIG_GLOBAL_PROPERTY\(qreal, base, 0.85\)|CONFIG_GLOBAL_PROPERTY\(bool, blur, true\)' shell/plugin/src/Caelestia/Config/appearanceconfig.hpp`

```
21:    CONFIG_PROPERTY(qreal, scale, 1)
56:    CONFIG_PROPERTY(qreal, scale, 1)
89:    CONFIG_PROPERTY(qreal, scale, 1)
154:    CONFIG_PROPERTY(qreal, scale, 1)
172:    CONFIG_GLOBAL_PROPERTY(qreal, scale, 1)
216:    CONFIG_GLOBAL_PROPERTY(qreal, base, 0.85)
233:    CONFIG_GLOBAL_PROPERTY(bool, blur, true)
```

(21 = `AppearanceRounding`, 56 = `AppearanceSpacing`, 89 = `AppearancePadding`,
154 = `AppearanceFont`, 172 = `AnimDurations` — **GLOBAL**, 216/233 =
`AppearanceTransparency`/`AppearanceConfig` — GLOBAL.)

### [C4] borderconfig.hpp — `sed -n '10,24p' shell/plugin/src/Caelestia/Config/borderconfig.hpp`

```
class BorderConfig : public settings::ObjectNode {
    CONFIG_NODE(BorderConfig, settings::ObjectNode)

    CONFIG_PROPERTY(int, thickness, 10)
    CONFIG_PROPERTY(int, rounding, 25)
    CONFIG_PROPERTY(int, smoothing, 20)

    Q_PROPERTY(int minThickness READ minThickness CONSTANT)
    Q_PROPERTY(int clampedThickness READ clampedThickness NOTIFY thicknessChanged)

public:
    [[nodiscard]] static int minThickness() { return 2; }

    [[nodiscard]] int clampedThickness() const { return std::max(minThickness(), m_thickness); }
};
```

### [C5] launcher maxShown — `rg -n 'CONFIG_PROPERTY\(int, maxShown' shell/plugin/src/Caelestia/Config/launcherconfig.hpp`

```
44:    CONFIG_PROPERTY(int, maxShown, 7)
```

### [C6] global-only shorthand and the setter's type-only hook — `sed -n '116,118p' shell/plugin/src/Caelestia/Settings/macros.hpp` and `sed -n '90,92p' shell/plugin/src/Caelestia/Settings/macros.hpp` and `sed -n '88,92p' shell/plugin/src/Caelestia/Settings/node.hpp` and `sed -n '133,141p' shell/plugin/src/Caelestia/Settings/node.cpp`

```
// Defines a global property on a node. Shorthand for .globalOnly = true.
#define SETTINGS_GLOBAL_PROPERTY(Type, name, defaultVal, ...)                                                          \
    SETTINGS_PROPERTY_IMPL(Type, name, true, DEFAULT_ARG(defaultVal), __VA_ARGS__)
---
    void set_##name(const Type& value) {                                                                               \
        if (rejectInvalidWrite(QStringLiteral(#name), value))                                                          \
            return; /* Skip writes of the wrong type */                                                                \
---
template <typename T> bool Node::rejectInvalidWrite(const QString& key, const T& value) const {
    Q_UNUSED(key)
    Q_UNUSED(value)
    return false; // Only QVariant unions can be given the wrong type
}
---
bool Node::rejectInvalidWrite(const QString& key, const QVariant& value) const {
    const auto* desc = schema().get(key);
    if (!desc || desc->accepts(value.metaType()))
        return false;

    qCWarning(lcSettings, "Type mismatch for %s, expected %s got %s", qUtf8Printable(pathFor(key)),
        qUtf8Printable(desc->typeString()), value.metaType().name());
    return true;
}
```

(Upstream's own history replaced an earlier no-op TODO hook
`if (!true /* TODO: validation */) return;` with the type-only
`rejectInvalidWrite` above — no numeric bounds were added, hence §1.1.)

### [C7] configDir / monitorConfigDir — `sed -n '11,18p' shell/plugin/src/Caelestia/Config/common.cpp`

```
QString configDir() {
    return QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation) + u"/caelestia"_s;
}

QString monitorConfigDir() {
    return configDir() + u"/monitors"_s;
}
```

### [C8] global file wiring — `sed -n '106,110p;131,131p' shell/plugin/src/Caelestia/Config/rootnodes.cpp`

```
    Type::Type(QObject* parent)                                                                                        \
        : Root(configDir() + QLatin1Char('/') + file, nullptr, parent)                                                 \
        , m_layers(monitorConfigDir(), file, this) {                                                                   \
        initLayer(this);                                                                                               \
    }                                                                                                                  \
SINGLETON_IMPL(ConfigSingleton, ConfigRoot, QStringLiteral("shell.json"), detail::ConfigKind::Shell)
```

### [C9] per-screen path — `sed -n '52,54p' shell/plugin/src/Caelestia/Settings/layerregistry.hpp`

```
template <LayerType T> QString LayerRegistry<T>::pathFor(const QString& name) const {
    return m_prefix + QLatin1Char('/') + name + QLatin1Char('/') + m_suffix;
}
```

### [C10] hot reload: watcher, debounces, retries — `sed -n '18,19p;26,38p' shell/plugin/src/Caelestia/Settings/settingsfile.cpp`

```
// Max retries for loads which fail due to malformed JSON, e.g. partial writes
constexpr int kMaxLoadRetries = 3;
    , m_watcher(new QFileSystemWatcher(this))
    , m_saveDebounce(new QTimer(this))
    , m_loadDebounce(new QTimer(this))
    , m_loadRetries(0) {
    m_saveDebounce->setSingleShot(true);
    m_saveDebounce->setInterval(500); // Save at most once every 500ms

    m_loadDebounce->setSingleShot(true);
    m_loadDebounce->setInterval(50); // Coalesce watcher events within 50ms
    QObject::connect(m_loadDebounce, &QTimer::timeout, this, &SettingsFile::onLoadDebounced);

    QObject::connect(m_watcher, &QFileSystemWatcher::fileChanged, this, &SettingsFile::onFileChanged);
    QObject::connect(m_watcher, &QFileSystemWatcher::directoryChanged, this, &SettingsFile::onDirChanged);
```

### [C11] shell-side save is QJsonDocument indented — `sed -n '167,169p' shell/plugin/src/Caelestia/Settings/settingsfile.cpp`

```
    const auto json = m_pendingWrite.value();
    const auto data = (json.isObject() ? QJsonDocument(json.toObject()) : QJsonDocument(json.toArray())).toJson();
    m_pendingWrite = std::nullopt;
```

(`toJson()` with no argument = `QJsonDocument::Indented` = 4 spaces; and the
shell's own dumps are sparse — `objectnode.hpp:20`
`QJsonValue toJson(bool sparse = true) const override;`.)

### [C12] bar scale floor + 4-way position — `sed -n '23,24p;33,39p' shell/modules/bar/BarWrapper.qml` and `rg -n 'name: "(left|right|top|bottom)"' shell/modules/bar/BarWrapper.qml`

```
    readonly property string position: Config.bar.position
    readonly property real barScale: Math.max(0.6, !isNaN(Config.bar.scale) ? Config.bar.scale : 1.0)
        if (position === "top")
            return Qt.rect(ox, oy, screen.width, contentWidth);
        if (position === "bottom")
            return Qt.rect(ox, oy + screen.height - contentWidth, screen.width, contentWidth);
        if (position === "left")
            return Qt.rect(ox, oy, contentWidth, screen.height);
        return Qt.rect(ox + screen.width - contentWidth, oy, contentWidth, screen.height);
168:                name: "left"
180:                name: "right"
192:                name: "top"
204:                name: "bottom"
```

### [C13] TaskbarPanel: bar scale stepper + livePreviews toggle — `sed -n '157,166p;178,183p' shell/modules/nexus/pages/panels/TaskbarPanel.qml`

```
        StepperRow {
            first: true
            label: qsTr("Bar scale")
            subtext: qsTr("Scales taskbar thickness and component sizing")
            value: GlobalConfig.bar.scale
            from: 0.6
            to: 1.6
            stepSize: 0.05
            onMoved: v => GlobalConfig.bar.scale = v
        }
        ToggleRow {
            text: qsTr("Live window previews")
            subtext: qsTr("Live thumbnails in hover/overview/alt-tab. Disable if screen sharing or camera in other apps (e.g. Vesktop) freezes")
            checked: GlobalConfig.bar.livePreviews
            onToggled: GlobalConfig.bar.livePreviews = checked
        }
```

### [C14] AppearancePage steppers — `sed -n '108,126p;141,148p;285,325p' shell/modules/nexus/pages/wallandstyle/AppearancePage.qml`

```
            StepperRow {
                label: qsTr("Border thickness")
                subtext: qsTr("Thickness of the shell border in pixels. Set to 0 for a borderless look")
                value: GlobalConfig.border.thickness
                from: 0
                to: 50
                stepSize: 1
                onMoved: v => GlobalConfig.border.thickness = v
                Layout.topMargin: Tokens.spacing.extraSmall / 2 - parent.spacing
            }
            StepperRow {
                label: qsTr("Corner radius scale")
                subtext: qsTr("Multiplies the shell's corner rounding")
                value: GlobalConfig.appearance.rounding.scale
                from: 0.5
                to: 2.0
                stepSize: 0.1
                onMoved: v => GlobalConfig.appearance.rounding.scale = v
                Layout.topMargin: Tokens.spacing.extraSmall / 2 - parent.spacing
            SliderRow {
                label: qsTr("Base opacity")
                valueLabel: Math.round(value * 100) + "%"
                value: GlobalConfig.appearance.transparency.base
                enabled: GlobalConfig.appearance.transparency.enabled
                onMoved: v => GlobalConfig.appearance.transparency.base = v
                Layout.topMargin: Tokens.spacing.extraSmall / 2 - parent.spacing
            }
            StepperRow {
                first: true
                Layout.fillWidth: true
                label: qsTr("Font scale")
                value: GlobalConfig.appearance.font.scale
                from: 0.5
                to: 2
                stepSize: 0.05
                onMoved: v => GlobalConfig.appearance.font.scale = v
            }

            StepperRow {
                Layout.fillWidth: true
                label: qsTr("Spacing scale")
                value: GlobalConfig.appearance.spacing.scale
                from: 0.5
                to: 2
                stepSize: 0.05
                onMoved: v => GlobalConfig.appearance.spacing.scale = v
            }

            StepperRow {
                Layout.fillWidth: true
                label: qsTr("Padding scale")
                value: GlobalConfig.appearance.padding.scale
                from: 0.5
                to: 2
                stepSize: 0.05
                onMoved: v => GlobalConfig.appearance.padding.scale = v
            }

            StepperRow {
                last: true
                Layout.fillWidth: true
                label: qsTr("Animation speed scale")
                value: GlobalConfig.appearance.anim.durations.scale
                from: 0.25
                to: 4
                stepSize: 0.05
                onMoved: v => GlobalConfig.appearance.anim.durations.scale = v
            }
```

### [C15] transparency slider clamps 0..1 — `sed -n '103,110p' shell/components/controls/SliderRow.qml`

```
            CustomMouseArea {
                function onWheel(event: WheelEvent): void {
                    const step = GlobalConfig.services.audioIncrement;
                    if (event.angleDelta.y > 0)
                        root.moved(Math.min(1, root.value + step));
                    else if (event.angleDelta.y < 0)
                        root.moved(Math.max(0, root.value - step));
                }
```

### [C16] dock icon size — `sed -n '54,63p' shell/modules/nexus/pages/panels/taskbar/BarDock.qml` and `rg -n 'configuredItemSize' shell/modules/bar/components/Dock.qml`

```
        StepperRow {
            Layout.fillWidth: true
            label: qsTr("Icon size")
            subtext: qsTr("Size of app icons in the dock")
            value: Config.bar.dock.iconSize
            from: 20
            to: Math.max(20, Tokens.sizes.bar.innerWidth)
            stepSize: 2
            onMoved: v => GlobalConfig.bar.dock.iconSize = v
        }
38:    readonly property real configuredItemSize: Math.max(16, Math.min(effectiveThickness, Config.bar.dock.iconSize || 32))
296:        property real itemSize: root.configuredItemSize
```

### [C17] launcher maxShown stepper — `sed -n '139,146p' shell/modules/nexus/pages/panels/LauncherPanel.qml`

```
        StepperRow {
            label: qsTr("Max items shown")
            value: Config.launcher.maxShown
            from: 1
            to: 20
            stepSize: 1
            onMoved: v => GlobalConfig.launcher.maxShown = v
        }
```

### [C18] notifsconfig.hpp in full (no "enabled" boolean) — `cat shell/plugin/src/Caelestia/Config/notifsconfig.hpp`

```
#pragma once

#include "../Settings/objectnode.hpp"
#include "common.hpp"

#include <qstring.h>

namespace caelestia::config {

class NotifsConfig : public settings::ObjectNode {
    CONFIG_NODE(NotifsConfig, settings::ObjectNode)

    CONFIG_GLOBAL_PROPERTY(bool, expire, true)
    CONFIG_GLOBAL_PROPERTY(QString, fullscreen, QStringLiteral("off"))
    CONFIG_GLOBAL_PROPERTY(QString, monitor, QStringLiteral("all"))
    CONFIG_GLOBAL_PROPERTY(int, defaultExpireTimeout, 5000)
    CONFIG_GLOBAL_PROPERTY(int, fullscreenExpireTimeout, 2000)
    CONFIG_PROPERTY(qreal, clearThreshold, 0.3)
    CONFIG_PROPERTY(int, expandThreshold, 20)
    CONFIG_GLOBAL_PROPERTY(bool, actionOnClick, false)
    CONFIG_PROPERTY(int, groupPreviewNum, 3)
    CONFIG_PROPERTY(bool, openExpanded, false)
    CONFIG_GLOBAL_PROPERTY(QString, position, QStringLiteral("auto"))
    CONFIG_GLOBAL_PROPERTY(int, maxPopups, 8)
    CONFIG_GLOBAL_PROPERTY(int, maxNotifs, 50)
};

} // namespace caelestia::config
```

### [C19] shell.qml has exactly two IpcHandlers — `rg -n 'IpcHandler|target:' shell/shell.qml`

```
50:        target: ShellState
60:        target: Translations
66:        target: Translations
82:    IpcHandler {
103:        target: "region"
106:    IpcHandler {
116:        target: "lock"
```

### [C20] monitorCenter has no QML consumer — `rg -n 'monitorCenter' shell -g '!*.hpp'`

```
shell/modules/bar/components/workspaces/Workspaces.qml:26:        // Removed manual monitorCenter logic as it's handled natively by Bar.qml layout zones
```

### [C21] import-policy lint facts — `sed -n '52,52p;123,125p' assistant/diagnostics/schema_lint.py`

```
FORBIDDEN_OS_ATTRS = ("system", "popen", "execv", "execve", "execvp", "spawnv", "spawnve", "fork")
def _iter_py_files() -> List[Path]:
    root = ASSISTANT_DIR
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
```

(`os.replace` is not in `FORBIDDEN_OS_ATTRS`; the rglob covers
`assistant/settings/**` automatically.)

### [C22] ALLOWED_IMPORTS.txt entries — `rg -v '^#|^$' assistant/ALLOWED_IMPORTS.txt`

```
json
re
os
sys
glob
pathlib
argparse
unittest
dataclasses
typing
difflib
math
collections
itertools
datetime
textwrap
ast
tempfile
http.client
```

### [C23] loader quarantine — `sed -n '113,116p;122,131p;144,147p;155,163p' shell/plugin/src/Caelestia/Settings/objectnode.cpp` and `sed -n '182,189p' shell/plugin/src/Caelestia/Settings/node.cpp`

```
    // Convenience macro for quarantine then skip
#define SKIP                                                                                                           \
    quarantineKey(key, v);                                                                                             \
    continue
        if (!desc) {
            const auto path = pathFor(key);
            qCWarning(lcSettings) << "Unknown option" << path;
            diagnostics << Diagnostic{
                DiagnosticType::UnknownOption,
                path,
                QStringLiteral("Unknown option %1").arg(key),
            };
            SKIP;
        }
        if ((m_globalOnly || desc->globalOnly()) && fallbackNode()) {
            warnGlobalSync(diagnostics, pathFor(key));
            SKIP;
        }
        auto val = desc->codec->decode(v);
        if (val.error) {
            const auto path = pathFor(key);
            qCWarning(
                lcSettings, "Error decoding option %s: %s", qUtf8Printable(path), qUtf8Printable(val.error->message));
            val.error->option = path;
            diagnostics << *val.error;
            SKIP;
        }
---
void Node::warnGlobalSync(QList<Diagnostic>& diagnostics, const QString& path) {
    qCWarning(lcSettings, "Global option definition %s found in overlay file, ignoring.", qUtf8Printable(path));
    diagnostics << Diagnostic{
        .type = DiagnosticType::GlobalOption,
        .option = path,
        .message = QStringLiteral("Global options should not be defined in overlay files"),
    };
}
```

(#806 factored the old inline global-option diagnostic block into
`Node::warnGlobalSync` (node.cpp:182-189) and hardened it — `rejectGlobalSync`
now refuses a whole sync onto a global-only overlay node, objectnode.cpp:86-88
— the quarantine semantics the planner relies on are unchanged.)

### [C24] existing layers' posture — `sed -n '50,50p;374,383p' assistant/diagnostics/engine.py`

```
COMMAND_PREFIX = "SUGGESTED_NOT_EXECUTED:"
def diagnose(text: str, rules: Optional[List[Dict[str, Any]]] = None, top: int = 3) -> Dict[str, Any]:
    """Run the full deterministic pipeline over one input blob.

    Verdicts:
      MATCH     — exactly one gate-passing rule, or a clear margin (>=2
                  points) over the runner-up.
      AMBIGUOUS — several candidates within the margin; report top N with
                  clarify probes. Never silently pick one.
      NO_MATCH  — nothing passed its gate; the honest answer is "I don't
                  know", plus pointers to diagnostic commands and Layer 2.
```

### [C25] scheme/wallpaper CLI — `sed -n '86,87p' src/bin/caelestia` and `sed -n '63,65p;80,81p' src/bin/caelestia-color`

```
  wallpaper [OPTS]             set the wallpaper and derive the palette from it
  scheme <list|get|set> [...]  manage the color scheme
```
```
  set [OPTS]            switch scheme. Without an argument nothing happens:
      -n, --name NAME     a named scheme, or "dynamic" for one derived from the
                          wallpaper
  -f, --file PATH       set the wallpaper and re-derive a dynamic scheme from it
  -p, --print [PATH]    print the scheme for a wallpaper, changing nothing.
```

(`caelestia-color` header: "State: $XDG_STATE_HOME/caelestia/{scheme.json,
wallpaper/, theme/}" — not shell.json.)

### [C26] durations scale multiplies base durations (lower = faster) — `rg -n 'Tokens\.anim\.durations\.scale' shell -g '*.qml'`

```
shell/components/controls/CircularIndicator.qml:68:            duration: manager.completeEndDuration * Tokens.anim.durations.scale
shell/components/controls/CircularIndicator.qml:95:        duration: manager.duration * Tokens.anim.durations.scale
shell/components/controls/CircularIndicator.qml:104:        duration: manager.completeEndDuration * Tokens.anim.durations.scale
shell/components/controls/AnimatedPasswordMask.qml:116:                    duration: 180 * Tokens.anim.durations.scale
```

### [C27] transparency.base is surface opacity — `sed -n '383,383p' shell/modules/drawers/ContentWindow.qml`

```
        opacity: GlobalConfig.appearance.pitchBlack ? 1 : (Colours.transparency.enabled ? Colours.transparency.base : 1.0)
```

### [C28] workspaces.shown is owned by a KWin sync loop — `sed -n '34,51p' shell/modules/nexus/pages/panels/taskbar/BarWorkspaces.qml`

```
        Connections {
            target: Kwin

            function onWorkspacesChanged() {
                let len = Kwin.workspaces.length;
                if (len > 0 && GlobalConfig.bar.workspaces.shown !== len) {
                    GlobalConfig.bar.workspaces.shown = len;
                }
            }
        }

        Component.onCompleted: {
let len = Kwin.workspaces.length;
if (len > 0 && GlobalConfig.bar.workspaces.shown !== len) {
    GlobalConfig.bar.workspaces.shown = len;
}

        }
```

### [C29] env-var allowlist precedent — `sed -n '48,48p' assistant/diagnostics/engine.py`

```
ENV_ALLOWLIST = ["HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"]
```

### [C30] blur live consumer — `sed -n '64,64p' shell/modules/nexus/WindowFactory.qml`

```
                Region { item: (GlobalConfig.appearance.transparency.enabled && GlobalConfig.appearance.blur) ? nexus : null }
```

### [C31] pitchBlack declaration, UI toggle and readers — `rg -n 'pitchBlack' shell/plugin/src/Caelestia/Config/appearanceconfig.hpp` and `sed -n '92,99p' shell/modules/nexus/pages/wallandstyle/AppearancePage.qml` and `rg -n 'pitchBlack' shell/modules/drawers/ContentWindow.qml shell/modules/background/BadAppleOverlay.qml shell/components/controls/Menu.qml`

```
231:    CONFIG_GLOBAL_PROPERTY(bool, pitchBlack, false)
---
            ToggleRow {
                first: true
                text: qsTr("Bezel mode (Pitch black)")
                subtext: qsTr("Make the shell pitch black to blend with display bezels")
                checked: GlobalConfig.appearance.pitchBlack
                onToggled: GlobalConfig.appearance.pitchBlack = checked
                Layout.fillWidth: true
            }
---
shell/components/controls/Menu.qml:155:                : (GlobalConfig.appearance.pitchBlack
shell/modules/drawers/ContentWindow.qml:383:        opacity: GlobalConfig.appearance.pitchBlack ? 1 : (Colours.transparency.enabled ? Colours.transparency.base : 1.0)
shell/modules/drawers/ContentWindow.qml:394:            color: GlobalConfig.appearance.pitchBlack ? "#000000" : root.surfaceColour
shell/modules/background/BadAppleOverlay.qml:45:                color: GlobalConfig.appearance.pitchBlack ? "#000000" : Colours.tPalette.m3surface
```

### [C32] notifs count keys: declarations, shipped steppers, live readers — `sed -n '13,25p' shell/plugin/src/Caelestia/Config/notifsconfig.hpp` and `sed -n '137,156p' shell/modules/nexus/pages/services/NotificationPreferencesPage.qml` and `rg -n 'maxPopups|maxNotifs' shell/modules/notifications/Content.qml shell/services/Notifs.qml`

```
    CONFIG_GLOBAL_PROPERTY(bool, expire, true)
    CONFIG_GLOBAL_PROPERTY(QString, fullscreen, QStringLiteral("off"))
    CONFIG_GLOBAL_PROPERTY(QString, monitor, QStringLiteral("all"))
    CONFIG_GLOBAL_PROPERTY(int, defaultExpireTimeout, 5000)
    CONFIG_GLOBAL_PROPERTY(int, fullscreenExpireTimeout, 2000)
    CONFIG_PROPERTY(qreal, clearThreshold, 0.3)
    CONFIG_PROPERTY(int, expandThreshold, 20)
    CONFIG_GLOBAL_PROPERTY(bool, actionOnClick, false)
    CONFIG_PROPERTY(int, groupPreviewNum, 3)
    CONFIG_PROPERTY(bool, openExpanded, false)
    CONFIG_GLOBAL_PROPERTY(QString, position, QStringLiteral("auto"))
    CONFIG_GLOBAL_PROPERTY(int, maxPopups, 8)
    CONFIG_GLOBAL_PROPERTY(int, maxNotifs, 50)
---
        StepperRow {
            label: qsTr("Max popup notifications")
            subtext: qsTr("Only the newest popups are shown; the rest stay in the sidebar")
            value: GlobalConfig.notifs.maxPopups
            from: 0
            to: 30
            stepSize: 1
            onMoved: value => GlobalConfig.notifs.maxPopups = Math.round(value)
        }

        StepperRow {
            last: true
            label: qsTr("Max stored notifications")
            subtext: qsTr("Older notifications are dropped when the limit is reached")
            value: GlobalConfig.notifs.maxNotifs
            from: 20
            to: 2000
            stepSize: 50
            onMoved: value => GlobalConfig.notifs.maxNotifs = Math.round(value)
        }
---
shell/modules/notifications/Content.qml:85:                values: Notifs.list.filter(n => n.popup && !n.closed).slice(0, Math.max(0, Math.floor(GlobalConfig.notifs.maxPopups)))
shell/services/Notifs.qml:27:    readonly property int notifCap: Math.max(1, GlobalConfig.notifs.maxNotifs)
```

### [C33] bar.dragThreshold — grounded but NOT a tool (see §16) — `sed -n '261p' shell/plugin/src/Caelestia/Config/barconfig.hpp` and `sed -n '107,116p' shell/modules/nexus/pages/panels/TaskbarPanel.qml` and `sed -n '185,207p' shell/modules/drawers/Interactions.qml`

```
    CONFIG_PROPERTY(int, dragThreshold, 20)
---
        StepperRow {
            last: true
            label: qsTr("Drag threshold")
            subtext: qsTr("Pixels dragged before the bar reveals")
            value: GlobalConfig.bar.dragThreshold
            from: 0
            to: 200
            stepSize: 5
            onMoved: v => GlobalConfig.bar.dragThreshold = v
        }
---
        // Show/hide bar on drag
        if (pressed && inBarArea(dragStart.x, dragStart.y)) {
            if (bar.position === "left") {
                if (dragX > Config.bar.dragThreshold)
                    visibilities.bar = true;
                else if (dragX < -Config.bar.dragThreshold)
                    visibilities.bar = false;
            } else if (bar.position === "right") {
                if (dragX < -Config.bar.dragThreshold)
                    visibilities.bar = true;
                else if (dragX > Config.bar.dragThreshold)
                    visibilities.bar = false;
            } else if (bar.position === "top") {
                if (dragY > Config.bar.dragThreshold)
                    visibilities.bar = true;
                else if (dragY < -Config.bar.dragThreshold)
                    visibilities.bar = false;
            } else if (bar.position === "bottom") {
                if (dragY < -Config.bar.dragThreshold)
                    visibilities.bar = true;
                else if (dragY > Config.bar.dragThreshold)
                    visibilities.bar = false;
            }
```

### [C34] transparency.enabled coupling — why it stays a dead-end — `sed -n '128,140p;222,245p' shell/modules/nexus/pages/wallandstyle/AppearancePage.qml`

```
            ToggleRow {
                text: qsTr("Transparency")
                subtext: qsTr("Enable transparency across the shell")
                checked: GlobalConfig.appearance.transparency.enabled
                onToggled: {
                    GlobalConfig.appearance.transparency.enabled = checked
                    if (!checked) {
                        GlobalConfig.appearance.blur = false
                    }
                }
                Layout.topMargin: Tokens.spacing.extraSmall / 2 - parent.spacing
                Layout.fillWidth: true
            }
---
            ToggleRow {
                text: qsTr("Background Blur")
                subtext: parent.isBbdxEnabled ? qsTr("Disabling has no effect if Better Blur dx is enabled") : qsTr("Enable a frosted glass effect by blurring the background")
                checked: parent.isBbdxEnabled ? true : GlobalConfig.appearance.blur
                enabled: GlobalConfig.appearance.transparency.enabled && !parent.isBbdxEnabled
                onToggled: {
                    bbdxFixProcess.running = true;
                    GlobalConfig.appearance.blur = checked
                    if (GlobalConfig.appearance.transparency.enabled && checked) {
                        // Hack to force Quickshell blur region to update when enabling blur
                        GlobalConfig.appearance.transparency.enabled = false
                        blurHackTimer.start()
                    }
                }

                Timer {
                    id: blurHackTimer

                    interval: 50
                    onTriggered: GlobalConfig.appearance.transparency.enabled = true
                }
                Layout.topMargin: Tokens.spacing.extraSmall / 2 - parent.spacing
                Layout.fillWidth: true
            }
```

### [C35] notifs timeout keys display seconds, store milliseconds (why they are not tools) — `sed -n '117,125p;180,188p' shell/modules/nexus/pages/services/NotificationPreferencesPage.qml`

```
        StepperRow {
            label: qsTr("Default timeout")
            subtext: qsTr("Seconds before a notification dismisses")
            value: GlobalConfig.notifs.defaultExpireTimeout / 1000
            from: 1
            to: 60
            stepSize: 1
            onMoved: value => GlobalConfig.notifs.defaultExpireTimeout = Math.round(value * 1000)
        }
        StepperRow {
            label: qsTr("Fullscreen timeout")
            subtext: qsTr("Milliseconds a notification stays over a fullscreen app")
            value: GlobalConfig.notifs.fullscreenExpireTimeout / 1000
            from: 1
            to: 30
            stepSize: 1
            onMoved: value => GlobalConfig.notifs.fullscreenExpireTimeout = Math.round(value * 1000)
        }
```

### [C36] showBadges: declaration, shipped toggle, live reader, badge visuals, release note — `sed -n '168,178p' shell/plugin/src/Caelestia/Config/barconfig.hpp` and `sed -n '75,82p' shell/modules/nexus/pages/panels/taskbar/BarDock.qml` and `sed -n '630,634p' shell/modules/bar/components/Dock.qml` and `rg -n 'showBadges' shell -g '*.qml'` and `rg -n 'badge\?\.|id: countBadge|id: progressBar' shell/modules/bar/components/Dock.qml` and `sed -n '55,60p' shell/modules/whatsnew/Entries.qml`

`sed -n '168,178p' shell/plugin/src/Caelestia/Config/barconfig.hpp`:

```
class BarDock : public settings::ObjectNode {
    CONFIG_NODE(BarDock, settings::ObjectNode)

    CONFIG_PROPERTY(bool, monitorCenter, true)
    CONFIG_PROPERTY(bool, recolourIcons, false)
    CONFIG_PROPERTY(bool, showBadges, true)
    CONFIG_PROPERTY(int, iconSize, 32)
    CONFIG_PROPERTY(bool, currentDesktopOnly, false)
    CONFIG_PROPERTY(bool, previewOnDesktop, true)
    CONFIG_GLOBAL_PROPERTY(QStringList, pinnedApps, QStringList({ u"firefox"_s, u"org.kde.dolphin"_s }))
};
```

`sed -n '75,82p' shell/modules/nexus/pages/panels/taskbar/BarDock.qml`:

```
        ToggleRow {
            Layout.fillWidth: true
            text: qsTr("Show app badges")
            subtext: qsTr("Show the count, progress and urgency an app publishes for its dock icon")
            checked: Config.bar.dock.showBadges
            onToggled: GlobalConfig.bar.dock.showBadges = checked
        }
```

`sed -n '630,634p' shell/modules/bar/components/Dock.qml`:

```
                    readonly property var badge: {
                        const dummy = LauncherEntry.revision;
                        if (!modelData || !(Config.bar.dock.showBadges ?? true))
                            return null;
                        return LauncherEntry.forApp(modelData.id);
```

`rg -n 'showBadges' shell -g '*.qml'` (the complete reader set — toggle plus
one live reader; nothing else in the shell reads it):

```
shell/modules/nexus/pages/panels/taskbar/BarDock.qml:79:            checked: Config.bar.dock.showBadges
shell/modules/nexus/pages/panels/taskbar/BarDock.qml:80:            onToggled: GlobalConfig.bar.dock.showBadges = checked
shell/modules/bar/components/Dock.qml:632:                        if (!modelData || !(Config.bar.dock.showBadges ?? true))
```

`rg -n 'badge\?\.|id: countBadge|id: progressBar' shell/modules/bar/components/Dock.qml`
(the badge visuals that switch on the reader — all null-safe):

```
469:                        opacity: (delegateItem.badge?.urgent ?? false) ? 0.35 : 0
674:                        id: countBadge
678:                        readonly property bool asDot: (delegateItem.badge?.count ?? 0) <= 0
680:                        visible: delegateItem.badge?.countVisible ?? false
696:                                const count = delegateItem.badge?.count ?? 0;
709:                        id: progressBar
711:                        visible: delegateItem.badge?.progressVisible ?? false
721:                            width: Math.round(parent.width * (delegateItem.badge?.progress ?? 0))
```

`sed -n '55,60p' shell/modules/whatsnew/Entries.qml`:

```
            "id": "dock_app_badges",
            "revision": 24,
            "icon": "badge",
            "title": qsTr("Dock App Badges"),
            "description": qsTr("Dock icons can now display the count, progress, and urgency published by running applications. Configure it under Settings -> Panels -> Taskbar -> Dock.")
        },
```

The schema walk that surfaced this key is reproducible with the shipped
enumerator (§10):

```
$ python3 assistant/settings/enumerate.py . | tail -5
# headers-total: 31
# headers-reachable-from-ConfigRoot: 21
# roots: 21
# scalar-leaves: 580
# list-leaves: 10
$ python3 assistant/settings/enumerate.py . --git 14a2fa99 | tail -5
# headers-total: 31
# headers-reachable-from-ConfigRoot: 21
# roots: 21
# scalar-leaves: 579
# list-leaves: 10
$ diff <(sorted keys at 14a2fa99) <(sorted keys at this checkout)
500a501
> bar.dock.showBadges
```

The only earlier checkout diffed against here (`14a2fa99`) predates the
`showBadges` merge by one commit range; the sorted-key diff shows exactly
one line added and none removed, so every other citation and verdict in §1
and §16 stands unchanged against the current schema.

---

## 10. Registry generation pipeline

The 18 rows in §1 are the leading, hand-frozen entries of a larger,
generated `TOOL_SPECS` list: **277 tools in 19 feature-area groups**, plus
explainability, a bounded undo history, named presets with a
preview-then-confirm gate, direct addressing for the 259 tools beyond the
frozen 18, and the same validated registry shipped into the shell itself as
a native QML service behind the sidebar AI assistant. This section and
§11-§15 describe that registry and the features built on it; §16 has the
decision record for what was left out.

### 10.1 The registry: an 18-tool hand-frozen core inside a 277-tool
generated whole (the enumeration pipeline)

The registry is not hand-maintained beyond its 18-tool core. It is
generated by a pipeline whose inputs are the shell's own sources, and whose
output is the committed artifact `tools.json` (loaded by `registry.py` at
import — the module's only I/O):

    shell/plugin/src/Caelestia/Config/*.hpp
        ── enumerate.py (macro-level walker) ──▶ 833 leaf rows
    shell/modules/nexus/pages/** (a full Nexus control survey)
        ── ui_ranges_data.py ──▶ 318 control rows
    curations.py: groups, exclusion rules, fixups, the frozen 18 pins
        ── build_registry.py (merge) ──▶ tools.json (deterministic,
           atomic tmp + os.replace; build_registry.py:352)

- `enumerate.py` walks the `CONFIG_SUBOBJECT` mount tree from `ConfigRoot`
  (and, separately, the derived `tokens` root) with comment/string/preprocessor
  masking and paren-balanced macro extraction; `Settings::Schema::build`
  semantics (Settings/schema.cpp:89-131) mean a class's serialized schema is
  exactly the macros in its own body — the one inheritance case
  (`IconFontStyleConfig : FontStyleConfig`, appearanceconfig.hpp:145)
  therefore exposes only `font.icon.extraLarge` and the inherited
  family/large/medium/small are recorded as an anomaly, not leaves.
- `ui_ranges_data.py` is the 318-row transcription of a full Nexus
  control survey (72 StepperRow, 188 ToggleRow, 26 SelectRow, 10 SliderRow,
  22 other control kinds across the nexus pages): the shipped control is
  what grounds every range and enum.
- `curations.py` holds every human decision: `GROUPS` (feature-area slugs,
  curations.py:47), `EXCLUSION_RULES` (the named safety rules,
  curations.py:163-256), `ENUM_FIXUPS` / `CORE_OVERRIDES` / `RANGE_FIXUPS`
  (survey corrections, below), `CORE_TOOLS` (the 18 core rows pinned
  byte-for-byte, curations.py:373), `EXPLAIN_RULES` (11, curations.py:501)
  and `PRESETS` (5, curations.py:603).

**The mechanical exposure rule.** A config leaf becomes a tool if and only
if (a) it is a scalar that survives the exclusion rules, (b) a shipped
scalar Nexus control touches it (that control's row supplies the grounded
range/enum), and (c) a stable name can be derived from its path — with
two-pass disambiguation so colliding basenames get full-path camel names
(e.g. `setSessionVimKeybinds`). No tool exists without its UI grounding:
every one of the 277 carries at least two citations, C++ declaration line
first, shipped control second (`ToolSpec.citations`, registry.py:99-101).
The build-time citation checker (`test_registry.py`) confirmed all 277:
the cited C++ line contains the property name, the cited UI file:line has
the key access within ±14 lines, 0 failures; a structural default check
re-parsed every `tools.json` default from its cited C++ declaration line —
0 mismatches.

**Exclusion taxonomy (the `not_exposed` table, 427 rows, 15 reason tags,
per-reason counts as regenerated from tools.json):**

| reason | count | why |
|---|---|---|
| no-shipped-control | 353 | no Nexus control touches this leaf; not exposed without a UI-grounded citation |
| ai-provider-selfconfig | 29 | the assistant must not reconfigure its own plumbing (`ai.*` models/providers/accounts) |
| ai-endpoints | 7 | network endpoints |
| filesystem-paths | 7 | `paths.*` redirection owned by the wallpaper/CLI surface |
| ai-credentials | 5 | plaintext API keys — never tools |
| dynamic-enum | 4 | SelectRow value lists that are dynamic or numeric-coded without per-value ids (defaultPlayer, language, profilePicShape x2) |
| kwinrc-companion-writes | 4 | the shipped control also writes kwinrc keys / installs a KWin script; a shell.json-only write would desync the stores |
| session-commands | 4 | command lists the session menu executes |
| session-icons | 4 | icon-name strings, no shipped range/format control |
| ai-internal-state | 2 | internally-managed state blobs |
| ai-executables | 2 | binaries/paths the shell executes |
| string-stepper | 2 | steppers that store transformed strings (e.g. HH:MM) |
| complex-control | 2 | chips list / read-only Repeater, not a scalar setter |
| master-switch | 1 | `enabled` — the ConfigRoot master switch; a bad write disables the entire shell |
| free-string | 1 | free-form string with no frozen enumeration |

The named safety rules live in `curations.EXCLUSION_RULES`
(curations.py:163-256); the catch-all and merge-time reasons
(no-shipped-control, complex-control, dynamic-enum, string-stepper,
free-string) are emitted by `build_registry.py` during the merge
(build_registry.py:108-190). The union is the 15-tag table above.

**RANGE_FIXUPS — unit conversions (curations.py:304-368).** Nine shipped
steppers DISPLAY a transformed value while the stored leaf carries another
unit; `tools.json` records the range in the STORED unit (the only unit a
shell.json write can carry), with the transforming lines cited: seconds
displayed / milliseconds stored, x1000 — `notifs.defaultExpireTimeout`
(NotificationPreferencesPage.qml:120), `notifs.fullscreenExpireTimeout`
(:183), `osd.hideDelay` (OsdPage.qml:88), `nexus.networkRescanInterval`
(ServicesPage.qml:114), `dashboard.resourceUpdateInterval`
(ServicesPage.qml:103); minutes / seconds, x60 — `services.arpcIdleTimeout`
(ArpcPage.qml:89); percent / fraction, /100 — `services.audioIncrement`
(ServicesPage.qml:155), `services.brightnessIncrement` (ServicesPage.qml:165),
`services.maxVolume` (ServicesPage.qml:176). Each citation's lines contain
the conversion arithmetic itself (e.g. `value: x/1000` / `Math.round(v*1000)`).

**ENUM_FIXUPS — the gpuType case (curations.py:261-280).** The Nexus
survey annotated the Services GPU SelectRow as dynamic; re-verification at
source showed a fixed literal — `gpuValues: ["", "NVIDIA", "GENERIC",
"None"]` (ServicesPage.qml:47) — so `services.gpuType` is a real enum tool
with exactly those values. (The same table corrects
`background.wallpaperFillMode`: the SelectRow's labels are Crop|Fit|Stretch
but the values it writes are the scaling ints [2, 1, 0],
WallpaperSettingsPage.qml:26.) Enum derivation precedence generally: C++
enum declarations (metaenum keys are the serialized form) win over annotated
UI lists; parenthetical annotations are stripped; numeric-coded SelectRows
become int ranges when contiguous (layoutType 0-1, maxFprintTries 1-5) or
int enums when not (easingType).

**Count reconciliation (re-derived by running the walker).** The config
tree yields 568 scalar leaves; the separately-persisted derived tokens tree
(shell-tokens.json, bound by `ConfigRoot::bindTokens`) yields 136;
568 + 136 = 704 = 277 tools + 427 not_exposed — every scalar leaf the
walker finds is accounted for exactly once. The 16 `QVariantMap` leaves
(`font.*.vaxes`) are `kind=map` rows outside the scalar table (the Nexus
survey's "584 scalar leaves incl. map-typed" = 568 + 16); the walker's 833
total rows = 103 subobject + 704 scalar + 16 map + 10 list nodes. An
earlier enumerator run (§10, appendix) counted 580 scalar leaves against
this walk's 584: the earlier macro set did not count
`CONFIG_GLOBAL_ENUM_PROPERTY`, of which exactly 4 leaves exist
(services.weatherUnits serviceconfig.hpp:30, sensorUnits :32, dataUnits
:34, clockFormat :46); 584 - 4 = 580.

**Resulting registry** (regenerated and verified): 277 tools in
19 groups — bar 58, dock 5, appearance 6, effects 9, animations 1,
notifications 13, launcher 18, lockscreen 14, wallpaper-scheme 36,
overview 16, osd 7, dashboard 21, sidebar 3, nexus 1, border 3, general 12,
services 17, utilities 27, audio 10 — by kind: 168 bool, 48 int, 42 float,
18 enum, 1 string (a font family; string tools carry `string_max_len`, not
a range, and are not settable through the planner yet). `tools.json`
regenerates byte-identical from the checkout (the drift guard in
`tests/test_registry.py`); `registry.GROUPS` exposes the 19 slugs in
display order.

## 11. Direct addressing vs the frozen 18-tool noun surface

The natural-language write surface is deliberately unchanged from the
18-tool core: the same fixed regex grammar, the same nouns, the same
verdicts — every #120-era sentence test passes unmodified. The 259
generated tools are reached by name, not by words:

- `--call NAME=VALUE` (cli.py:406-412): repeatable direct tool call; VALUE
  is JSON (a bare token that fails JSON parsing is a plain string, so enums
  work unquoted); multiple `--call` flags compose one multi-op plan through
  the ordinary planner → render → `--apply` path. Any rejected entry
  (unknown tool, out-of-range, bad enum, non-finite number, string tool)
  makes the run exit 1 **even in dry-run**; usage errors (missing `=`,
  `--call` + positional sentence together) exit 2.
- `--tool NAME` (cli.py:402-405): a detail card — path, group, kind,
  validation, default, step, nouns, and every citation line
  `file:line — what it evidences`.
- `--list-tools [--group SLUG]` (cli.py:394-401): the full 277-tool table
  or one feature area's slice, with per-group subtotals when unfiltered.

Two guards in `parser.py` keep the frozen surface frozen against a registry
15x its size:

- `_noun_matched` (parser.py:228-239): a noun-silent tool (nouns == (),
  i.e. every one of the 259 generated tools) matches NOTHING — `all([])` is
  vacuously True, so the empty noun list is guarded explicitly instead of
  acting as a universal match.
- the size-class filter (parser.py:94-105): `_SIZE_TOOLS` admits only
  noun-bearing tools, so the targetless "make it smaller" candidate list
  stays exactly the 18-tool set (`_ANIM_TOOLS` / `_TRANS_TOOLS`
  likewise).

The 18 core tools keep their exact names, paths, kinds, defaults, ranges,
steps, global-only flags and nouns, and lead `TOOL_SPECS` (registry.py:67-86,
:161-172); a loud import-time guard fails if `tools.json` ever loses one
(registry.py:223-229), and a golden test pins all their fields.

## 12. The in-shell QML service (shell/services/SettingsTools.qml)

**Architecture decision:** a native QML singleton, not a Python process
bridge. Grounds, all read in this checkout:

1. Settings writes in this shell are property assignments —
   `GlobalConfig.bar.scale = v` (TaskbarPanel.qml:165),
   `GlobalConfig.bar.persistent = checked` (TaskbarPanel.qml:71-72),
   `GlobalConfig.bar.dock.iconSize = v` (BarDock.qml:62) — auto-persisted
   by ChangeBatcher's queued flush (changebatcher.cpp:8-25). The service
   does exactly that, in-process, type-safe, with live NOTIFY propagation.
2. No runtime Python dependency and no requirement that the `assistant/`
   overlay be installed on the user's system (install.sh does not ship it).
3. No process-spawn per tool call inside the agent loop, no stdout/stderr
   plumbing on a safety-critical path (the sidebar's existing tool loop
   spawns processes for its other tools — parseTextToolCalls() :824,
   runAgentCommand() :865 in AiAssistant.qml).
4. The confirmation flow needs in-chat interactive UI (a preview card with
   Apply/Cancel) — only possible natively.
5. Single-sourced registry: the Python `tools.json` is canonical; its
   tables are embedded verbatim into the QML, and a Python test
   cross-checks the two for exact equality — no drift possible without
   failing the suite.
6. The Python layer stays the offline CLI (model-less NL planning and the
   test surface); the QML service is the runtime surface where the model
   does NL→tool-call mapping.

**The service** (833 lines, generated from a persisted template;
`pragma Singleton` at :1-2, header :4-23):

- `toolTable` (277 rows incl. citations, :56), `presetTable` (5),
  `explainTable` (11) — generated blocks marked DO NOT EDIT BY HAND.
- lookups: `toolInfo` / `toolsInGroup` / `listTools` / `get`
  (:379-417).
- `validate()` (:439): mirrors planner.py's set-branch semantics —
  out-of-range REJECTED (never clamped), type mismatches rejected (never
  coerced), enums accepted case-insensitively and canonicalized to the
  metaenum key, mirroring `EnumCodec::decode` (codecs.cpp:249-257).
- `readPath` / `writePath` (:482-512): the GlobalConfig bracket-walk —
  the same write idiom every Nexus page uses.
- `buildPlan` / `request` / `previewOf` / `confirmPlan` / `cancelPlan` /
  `applyOps` (:514-602): the issue-#120 policy — a single-op request
  applies directly; a multi-op request becomes `pendingPlan` + a confirm
  card; a mid-apply failure rolls back what was already written.
- bounded undo: `maxHistory: 12` (:37), `historyPath`
  `${Paths.state}/assistant-settings-history.json` (:38; Paths.state is
  ~/.local/state/caelestia, Paths.qml:16), persisted via a `FileView`
  (:818); `historyEntries` / `undo(steps)` / `undoById(id)`
  (:621-643).
- `explain()` (:759) and `presetList` / `requestPreset` (:802-816), the
  same rule/answer spec as the Python side (§13, §15).

**The AiAssistant.qml wiring** (+236/-7 lines): 8 settings meta-tools
declared to the model in the system prompt at :2329 —
`caelestia_setting_list` / `_get` / `_set` / `_undo` / `_history` /
`_explain`, `caelestia_preset_list` / `_apply` — with the instruction that
multi-change requests are confirmed, never claimed done; dispatch branches
for all 8 (e.g. :2149, :2199, :2206, :2218) calling the service
synchronously in-process; five new chat-model roles (`isSettingsPlan`,
`planLabel`, `planOps`, `planResolved`, `planResult`) threaded through all
append sites; the delegate renders the confirm card ("I found several
changes that match your request:" + per-op "path: from -> to" + Apply /
Cancel TextButtons at :3186 / :3193); `showSettingsConfirmCard` (:1781)
enforces the one-pending-card policy — a newer request supersedes an older
pending card as cancelled-without-write (`resolveSettingsCard(false,
true)`, :1785, :1802).

**Verification honesty:** no Qt toolchain exists in the build environment —
the QML was NOT compiled or run. The shipped guards are static
(`tests/test_qml_service.py`, 6 tests): table byte-identity vs tools.json
via an independent mini-renderer, row count == TOOL_COUNT, bracket balance
outside strings/comments, a 19-function API-surface pin (everything the
AiAssistant patch calls), the maxHistory bound, and confirm-policy
markers. Runtime behaviour stays unverified until a maintainer loads the
shell — stated here, plainly, as the one open item this document leaves
for human review.

## 13. Explainability (`explain.py` — read-only, never writes)

- **Effective values:** the state reader takes the file value, else the
  registry default — the same fallback semantics ConfigObject gives the
  QML side, so an unset key explains as its default.
- **Predicate grammar** (`_eval_when`, explain.py:118-149): `path == value`
  / `!=` / `>` / `<`, joined by ` and ` — the same restricted grammar the
  QML service implements. An unknown state key makes the rule NOT fire.
- **Answer template spec** (`_render`, explain.py:162-191): `{dotted.path}`
  → the formatted value; `{cite}` / `{citeN}` → citations; `{a|b}`
  alternation resolved by the first numeric value in the template (> 1
  picks the first option — "slower|faster" for durations.scale).
- **Query resolution** (`resolve_spec`, explain.py:194+): a dotted path or
  tool name resolves directly; plain-words questions reuse the parser's
  own noun matcher (write and read surfaces share one noun grammar) plus
  two READ-ONLY refinements the frozen write path does not get —
  `EXPLAIN_SYNONYMS` (explain.py:38-48: blurry/fuzzy→blur,
  laggy/sluggish→animations, the hide-family→auto hide) and
  `EXPLAIN_PREFERENCES` (explain.py:53-64: big/large/huge/small/tiny→
  setBarScale, giant→setDockIconSize, the slow/fast family→
  setAnimationSpeed) — and a last-position phenomenon heuristic: in "why
  is my X so Y", the candidate whose noun matches LATEST in the sentence
  is the phenomenon; the subject ("dock" in "why is my dock blurry") is
  incidental. Ambiguity that survives does not guess.
- **The rules** (`EXPLAIN_RULES`, 11, curations.py:501-595; mirrored in
  tools.json and the QML explainTable): every citation verified at source —
  BlurOffsets.qml:17; Colours.qml:418-419;
  ContentWindow.qml:374/383/394; shell/components/effects/AmbientGlow.qml:34;
  appearanceconfig.cpp:209; BarWrapper.qml:24/27/62.
- **Offline honesty:** rules referencing the live session flags
  `_gamemode` / `_light` cannot fire from the CLI (the file cannot know a
  runtime flag) — they fall through to the value readback with an honest
  note instead of guessing; the QML service evaluates the same rules with
  the live flags (GameMode.enabled, Colours.light).
- **No fabricated "Glass Mode":** issue #120's example answer says "Blur is
  enabled because Glass Mode is currently active" — but "Glass Mode" does
  not exist in this tree (grep across shell/ = 0 hits at 70ee7da). The
  real gate is `GlobalConfig.appearance.transparency.enabled &&
  GlobalConfig.appearance.blur` (drawers/blur/BlurOffsets.qml:17), so the
  shipped answer is: "Blur is enabled because transparency is currently
  active and appearance.blur is on — the blur regions gate on both
  (shell/modules/drawers/blur/BlurOffsets.qml:17)."

## 14. The bounded undo history (`history.py`)

- **Schema:** `{"next_id": int, "entries": [...]}` (newest first) persisted
  as a sibling of the target at `<target>.assistant-history.json`
  (history.py:18-20, :36); each entry is
  `{"id", "at" (ISO-8601), "label", "ops": [{"path", "old", "new"}]}`.
- **Bound:** `MAX_ENTRIES = 12` (>= the required 10; oldest evicted FIFO,
  history.py:37).
- **Recording:** `applier.apply(..., label=...)` captures the pre-merge old
  values and records the entry only AFTER a successful write — a failed
  write leaves no phantom entry (applier.py:227-229). Labels carry the
  request sentence, "direct --call invocation", or "preset: X".
- **Undo-consumes semantics:** `undo(steps)` / `undo_by_id(id)` build the
  reverse plan and hand it to `applier.apply(record_history=False)` — an
  undo consumes entries and is never itself recorded; redo is deliberately
  not offered (the issue asks for undo).
- **Undo-of-create:** `applier._deep_unset` (applier.py:92) REMOVES a key
  that the undone apply created (pruning empty parents) instead of writing
  null — the shell then falls back to the C++ default; test_history
  cross-checks via `explain()` that the effective value reads back as the
  default.
- **Write scope:** the applier remains the package's only writer, and its
  scope is exactly four sibling paths (applier.py:3-16): the target
  itself (transient `.assistant-tmp` + atomic `os.replace`), the
  single-slot `.assistant-backup` (one-level `--restore`), the removed
  tmp, and `.assistant-history.json`. The directory-snapshot tests in
  `test_safety.py` assert exactly these four paths and no others.

## 15. Presets and the confirmation gate (`presets.py`, `cli.py`)

- **Pure bundles:** a preset is STRICTLY a list of already-validated tool
  calls. The data lives in `curations.PRESETS` → tools.json
  (`registry.PRESETS`); `build_registry._preset_value_ok`
  (build_registry.py:68) FAILS THE BUILD if any call violates its tool's
  validation; `presets.preset_ops()` expands a preset to ordinary planner
  ops — no bespoke writer, no unvalidated code path (presets.py:44-60).
- **The five presets** (curations.py:603-675): `compact`, `minimal`,
  `gaming`, `battery-saver`, `macos-like` — the issue's Nexus-integration
  list verbatim ("Optimize for gaming", "Optimize for battery life",
  "Make this look more like macOS", "Make this look more minimal") plus
  compact. (The two §3.7 NL-trigger presets are a separate, older
  mechanism on the write path and are unaffected by this one.)
- **The gate:** `--confirm` (cli.py:443-448). Every MULTI-op plan —
  `--call` bundles, NL sentences, presets — renders the issue's verbatim
  preview shape ("I found several changes that match your request:" +
  "- path: old -> new" lines + "Apply these changes?") and is written only
  with `--confirm` (explicit second consent) or an interactive y/N on a
  tty; refusal exits 1 with nothing written (file bytes unchanged —
  pinned by tests). **Single-op applies remain direct**, exactly as the
  issue frames it ("For requests that affect multiple settings... ask for
  confirmation before applying them"). The QML side implements the same
  policy with the confirm card (§12).

## Test surface: additional coverage (§10-§15)

Six test files in `assistant/settings/tests/` cover the features in this
section (method counts as measured in this checkout): `test_registry.py`
(15 — the 18-tool core's golden preservation, the 277/427 count pins,
noun-silence, lookups, rendering, structural guards, citation drift guards
incl. regeneration byte-identity), `test_cli_calls.py` (27 — direct
addressing), `test_explain.py` (15), `test_history.py` (12),
`test_presets.py` (11), `test_qml_service.py` (6 — the QML static guards).
The four core-pipeline files (`test_parser.py`, `test_planner.py`,
`test_applier.py`, `test_safety.py`) hold 38 + 13 + 14 + 16 tests,
including the sibling-scope pin covering §14's fourth write path. Settings
suite: **167 tests**; the five assistant suites together: 17 + 18 + 48 +
13 + 167 = **263**; repo gate `bash tests/run-tests.sh`: 20/20 test files
from the repo root.

Three drift guards keep the generated artifacts honest: the count pins
(277/427/per-group), the all-cited-lines re-verification inside the suite,
and the regeneration byte-identity check. The QML tables carry a fourth:
byte-identity vs tools.json via the independent mini-renderer.
