---
name: Rory Web Chat
description: A flat, quiet, teal-accented chat surface for fast, deterministic answers.
colors:
  signal-teal: "oklch(0.5 0.12 195)"
  on-signal-teal: "oklch(0.99 0.005 195)"
  teal-wash: "oklch(0.94 0.03 195)"
  cool-paper: "oklch(0.975 0.006 250)"
  clean-sheet: "oklch(0.995 0.003 250)"
  night-ink: "oklch(0.24 0.02 255)"
  slate-note: "oklch(0.47 0.02 255)"
  hairline: "oklch(0.89 0.01 250)"
  control-edge: "oklch(0.62 0.02 255)"
  alert-red: "oklch(0.5 0.17 27)"
typography:
  display:
    fontFamily: "ui-rounded, 'SF Pro Rounded', system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', sans-serif"
    fontSize: "clamp(1.6rem, 5vw, 2.25rem)"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: "ui-rounded, 'SF Pro Rounded', system-ui, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "ui-rounded, 'SF Pro Rounded', system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "ui-rounded, 'SF Pro Rounded', system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.02em"
rounded:
  tail: "4px"
  option: "10px"
  bubble: "14px"
  field: "22px"
  pill: "999px"
spacing:
  xs: "0.5rem"
  sm: "0.75rem"
  md: "1rem"
  lg: "1.5rem"
components:
  bubble-me:
    backgroundColor: "{colors.signal-teal}"
    textColor: "{colors.on-signal-teal}"
    rounded: "{rounded.bubble}"
    padding: "0.55rem 0.95rem"
  bubble-rory:
    backgroundColor: "{colors.clean-sheet}"
    textColor: "{colors.night-ink}"
    rounded: "{rounded.bubble}"
    padding: "0.65rem 0.95rem"
  chip:
    backgroundColor: "{colors.clean-sheet}"
    textColor: "{colors.night-ink}"
    rounded: "{rounded.pill}"
    padding: "0.5rem 0.95rem"
    height: "2.5rem"
  chip-hover:
    backgroundColor: "{colors.teal-wash}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.slate-note}"
    rounded: "{rounded.pill}"
    padding: "0.4rem 0.9rem"
    height: "2.25rem"
  button-send:
    backgroundColor: "{colors.signal-teal}"
    textColor: "{colors.on-signal-teal}"
    rounded: "{rounded.pill}"
    size: "2.75rem"
  input-message:
    backgroundColor: "{colors.clean-sheet}"
    textColor: "{colors.night-ink}"
    rounded: "{rounded.field}"
    padding: "0.65rem 1rem"
    height: "2.75rem"
---

# Design System: Rory Web Chat

## Overview

**Creative North Star: "The Quick Counter"**

A fast, honest service desk. You ask, Rory answers, and nothing is performed in between. The interface is a single column on a cool paper-tinted ground: your messages are solid teal, Rory's answers are plain white sheets with a hairline border. The only character comes from the speech-bubble avatar and the teal that follows it everywhere.

The system is deliberately plain because Rory is not an AI and must never look like one. Fixed tools produce fixed answers, so the surface stays calm and gets out of the way: tone and borders create structure, never shadows or ornament. Motion is a short arrival and a typing pulse.

**Key Characteristics:**
- Flat at rest: hairline borders and tonal layers, no shadows.
- One accent (Signal Teal) that always means "you" or "act".
- Rounded system face, small type steps, generous line height for reading replies.
- Pill-shaped controls, 14px message bubbles with a 4px "tail" corner.
- Light and dark follow the system setting; both are first-class.

## Colors

A tinted-neutral ground with one saturated teal. Values below are the light theme; dark values are listed per color.

### Primary
- **Signal Teal** (oklch(0.5 0.12 195); dark oklch(0.78 0.12 195)): the user's message bubbles, the send button, the avatar, links in replies, the focus ring, the caret and text selection. It marks the person's own actions and Rory's identity; nothing else is teal.
- **On Signal Teal** (oklch(0.99 0.005 195); dark oklch(0.2 0.03 195)): text and icons on Signal Teal, and the avatar's eyes and smile.
- **Teal Wash** (oklch(0.94 0.03 195); dark oklch(0.3 0.04 195)): hover and selected fill for chips and typeahead rows, and the soft focus halo around the input.

### Neutral
- **Cool Paper** (oklch(0.975 0.006 250); dark oklch(0.19 0.015 255)): the page ground.
- **Clean Sheet** (oklch(0.995 0.003 250); dark oklch(0.24 0.018 255)): Rory's reply bubbles, chips, input and typeahead list. Always one tonal step above the ground.
- **Night Ink** (oklch(0.24 0.02 255); dark oklch(0.94 0.008 250)): body text.
- **Slate Note** (oklch(0.47 0.02 255); dark oklch(0.72 0.015 250)): secondary text, timestamps, placeholders, ghost-button labels. At least 6.3:1 on Cool Paper.
- **Hairline** (oklch(0.89 0.01 250); dark oklch(0.32 0.02 255)): reply-bubble borders and dividers.
- **Control Edge** (oklch(0.62 0.02 255); dark oklch(0.55 0.02 255)): the border of every control (message input, chips, ghost buttons, typeahead list). About 3.4:1 against the ground in light and 3.4–3.8:1 in dark, so controls are visible to low-vision users.

### Semantic
- **Alert Red** (oklch(0.5 0.17 27); dark oklch(0.76 0.14 27)): error bubbles only (border and text).

### Named Rules
**The One Voice Rule.** Teal means "you" or "do something". Reply content, labels and chrome never use it, with one exception: links inside replies.

**The Tinted Neutral Rule.** Neutrals carry a hint of the cool hue (chroma 0.003–0.02 at hue 250–255). Never pure gray, never pure white or black.

## Typography

**Display, Title, Body, Label Font:** the platform rounded UI face (`ui-rounded`, then SF Pro Rounded, then `system-ui`). No web font is loaded.

**Character:** friendly and brief. Rounded terminals soften a plain system face so replies feel approachable without an invented voice.

### Hierarchy
- **Display** (700, clamp(1.6rem, 5vw, 2.25rem), 1.15, -0.02em): the intro headline only. Balanced wrapping.
- **Title** (700, 1.05rem, 1.2): the "Rory" name in the header.
- **Body** (400, 1rem, 1.55): messages. Replies keep their own line breaks and wrap long words; the bubble caps at 36rem, about 60ch.
- **Label** (600, 0.75rem, 0.02em): the name row above each reply; timestamps use 0.75rem at weight 400 with tabular numerals.

### Named Rules
**The Weight Over Size Rule.** The header title is only 1.05× the body; weight carries the difference. Do not enlarge chrome text to add hierarchy.

## Layout

One conversation column, centered at 44rem, inside regions that span the full viewport: the header (with its hairline rule), the scrolling conversation (scrollbar at the viewport edge), the dock and the composer all run edge to edge and keep their content in the column. Horizontal padding is at least 1rem and respects safe-area insets. The page fills the dynamic viewport height.

Rhythm groups by turn: a question and its answer sit 0.5rem apart, and your next message starts a new turn 1.5rem later. Chips and actions use 0.5rem. The composer sits under the dock.

The typeahead and quick-reply chips live in the layout above the input, never over the conversation, so the log shrinks and is re-pinned to the latest reply. At 30rem and below the header subtitle hides and "What can I ask?" collapses to "Help". No horizontal scroll at 320px.

## Elevation & Depth

Flat by default. Depth is conveyed by tone (Clean Sheet on Cool Paper) and 1px Hairline borders, never by shadow. The only non-border emphasis is the 3px Teal Wash halo on the focused input.

### Named Rules
**The Flat-At-Rest Rule.** No `box-shadow` on bubbles, chips, lists or buttons. Choose either a border or a tonal step to separate a surface, never both a border and a soft shadow.

## Shapes

Rounded and friendly with one crisp detail. Message bubbles are 14px with a single 4px corner at the speaker's side (the "tail"): bottom-right for the user, top-left for Rory. Controls are pills (999px); the text input is 22px and grows to a rounded block when multi-line; typeahead rows are 10px inside a 14px list. The avatar is a speech-bubble silhouette with a tail at bottom-left.

## Components

### Message bubbles
- **Yours:** Signal Teal fill, On Signal Teal text, 14px with a 4px bottom-right corner, padding 0.55rem 0.95rem, max 85% of the column.
- **Rory's:** Clean Sheet fill, 1px Hairline border, 14px with a 4px top-left corner, padding 0.65rem 0.95rem. Above it, a name row: 24px avatar, "Rory", and a muted "· Tool" label naming which tool answered.
- **Error:** the same bubble with Alert Red border and text, plus a ghost "Try again" button.
- **Under each:** a 0.75rem muted timestamp; on Rory's replies a muted "Copy" text button beside it (44px target on touch screens). Copy results and "Rory is typing" are announced through a hidden status region.
- **Arrival:** 0.35s fade and 6px rise, exponential ease-out. With reduced motion there is no animation and the typing dots stay as three solid dots.

### Chips
- **Style:** pill, Clean Sheet fill, 1px Control Edge border, 0.9375rem text, 41px tall (36px in the quick-reply row; 44px on touch screens for every chip).
- **Hover:** Teal border and Teal Wash fill; press scales to 0.97.
- **Use:** intro examples and one-tap next steps (again, quit, help).

### Buttons
- **Ghost (header actions, retry):** transparent, Control Edge border, Slate Note label, pill, 36px tall (44px on touch screens); hover darkens the label to Night Ink and the border to Slate Note.
- **Send:** 44px Signal Teal circle with an up-arrow; disabled at 35% opacity; hover lifts 1px.

### Inputs / Fields
- **Message box:** Clean Sheet fill, 1px Control Edge border, 22px radius, grows with content to 8rem, Slate Note placeholder (rotating real examples), Signal Teal caret.
- **Focus:** border turns Signal Teal with a 3px Teal Wash halo.
- **Typeahead:** a Clean Sheet list with a Control Edge border above the input, exposed as a combobox (role, expanded state and result count announced); the active row is Teal Wash and the matched text is bold. Rows are 44px on touch screens.

### Typing indicator
Three 6px Slate Note dots pulsing in sequence inside a Rory bubble (solid, not pulsing, under reduced motion).

## Do's and Don'ts

### Do:
- **Do** keep Signal Teal for the user's own messages, the send button, the avatar, focus and links only.
- **Do** separate surfaces with one Hairline border or one tonal step, and give controls the stronger Control Edge.
- **Do** keep every tap target at least 36px tall, and 44px on touch screens, and show a 2px Signal Teal focus ring on `:focus-visible`.
- **Do** honor `prefers-reduced-motion` and `prefers-color-scheme`.
- **Do** show which tool produced an answer and give honest, specific example phrases.

### Don't:
- **Don't** use shadows, glows or glass on bubbles, chips or lists.
- **Don't** tint Rory's replies teal or add gradients, colored side borders or decorative icons.
- **Don't** write copy that implies open-ended AI ("ask anything"); name real capabilities.
- **Don't** use emoji as interface icons (emoji belong to reply content only); draw icons as SVG.
- **Don't** overlay the typeahead on the conversation.
