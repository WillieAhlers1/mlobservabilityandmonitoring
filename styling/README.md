# Tredence Theme Kit

Reusable design tokens and base components for theming Flask prototypes with Tredence's design language.

## What's confirmed vs. approximated

Pulled directly from tredence.com's public brand page:
- **Primary color:** bright orange
- **Secondary colors:** teal and green ("growth and analytical mindset")
- **Typeface:** Poppins, in Light / Regular / Medium / Bold / ExtraBold
- **Logo:** a "T" with a 60-degree angled cut on the top right
- **Visual tone:** clean, confident, generous whitespace, minimal corporate style, friendly photography

Tredence's exact hex/Pantone values live in their internal brand guide PDF (linked from tredence.com/our-brand as "Download the Brand Asset"), which was too large to pull in automatically. The hex values in `tredence-theme.css` are close, professionally reasonable stand-ins built from the confirmed palette (bright orange primary, teal + green secondary, dark navy neutral). If you get your hands on the internal brand guide, just swap the `--tr-orange`, `--tr-teal`, and `--tr-green` values at the top of the CSS file and everything downstream (buttons, badges, cards, nav) updates automatically.

## Files

- `tredence-theme.css` — all design tokens (CSS custom properties) plus base component styles: navbar, buttons, cards, badges, forms, tables, hero, footer.
- `base.html` — a Jinja base layout showing the theme wired up, meant to be extended by your other templates with `{% extends "base.html" %}`.

## Wiring into your Flask app

1. Copy `tredence-theme.css` into `static/css/tredence-theme.css`.
2. Copy `base.html` into `templates/base.html`.
3. Extend it from your pages:

```jinja
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
  <h2>Your page content</h2>
{% endblock %}
```

## Usage notes

- Use the `--tr-*` CSS variables anywhere you need brand colors, rather than hardcoding hex, so future palette corrections only touch one file.
- `.tr-btn--primary` (orange) is the main call-to-action style; `.tr-btn--teal` and `.tr-btn--secondary` are for secondary actions.
- `.tr-badge--orange/teal/green` map to the three brand accent colors for status tags, labels, etc.
- The navbar mark (`.tr-navbar__mark`) approximates the angled-cut "T" logo shape using `clip-path`. Swap in the real Tredence logo SVG/PNG if you have access to brand assets.
