"""Named widget themes for the Ariadex companion windows.

This module owns every presentation token (colors, spacing, fonts) used
by the mini-player and hub widgets. Layout lives in ``companion.py``;
paint lives here. Widgets ask for a role (``frame``, ``label``,
``button``, ``text_input``, ...) and receive options from the active
``Theme`` — no color literal may live in widget-construction code.

The ``dark`` theme preserves the historical dark values exactly; the
``light`` and ``contrast`` themes are additive alternatives selected
through the ``theme`` config key. Unknown names fall back to ``dark``.
"""

import dataclasses


@dataclasses.dataclass(frozen=True)
class Theme:
    """One complete widget palette plus text metrics."""

    name: str
    window_bg: str
    fg: str
    bright_fg: str
    muted_fg: str
    soft_fg: str
    accent_fg: str
    link_fg: str
    input_bg: str
    input_fg: str
    cursor_bg: str
    selection_bg: str
    button_bg: str
    button_fg: str
    button_active_bg: str
    button_active_fg: str
    press_bg: str
    press_active_bg: str
    success_bg: str
    success_active_bg: str
    danger_active_bg: str
    danger_active_fg: str
    log_bg: str
    log_fg: str
    trough_bg: str
    row_pady: int
    text_spacing: tuple[int, int, int]
    header_font: tuple[str, int, str]
    small_font: tuple[str, int, str]


DARK = Theme(
    name="dark",
    window_bg="#20242b",
    fg="#c9d1d9",
    bright_fg="#f3f4f6",
    muted_fg="#8b949e",
    soft_fg="#9aa4b2",
    accent_fg="#7dd3a8",
    link_fg="#7db8f0",
    input_bg="#14171c",
    input_fg="#c9d1d9",
    cursor_bg="#c9d1d9",
    selection_bg="#3b82f6",
    button_bg="#2b313a",
    button_fg="#f3f4f6",
    button_active_bg="#3b82f6",
    button_active_fg="#ffffff",
    press_bg="#3b82f6",
    press_active_bg="#2563eb",
    success_bg="#22c55e",
    success_active_bg="#16a34a",
    danger_active_bg="#9b3d52",
    danger_active_fg="#ffffff",
    log_bg="#14171c",
    log_fg="#c9d1d9",
    trough_bg="#2b313a",
    row_pady=2,
    text_spacing=(2, 0, 2),
    header_font=("TkDefaultFont", 10, "bold"),
    small_font=("TkDefaultFont", 9, "normal"),
)

LIGHT = Theme(
    name="light",
    window_bg="#eef1f4",
    fg="#1f2328",
    bright_fg="#0b0d10",
    muted_fg="#5b6570",
    soft_fg="#4b5563",
    accent_fg="#0a7a45",
    link_fg="#0b5cc0",
    input_bg="#ffffff",
    input_fg="#1f2328",
    cursor_bg="#1f2328",
    selection_bg="#3b82f6",
    button_bg="#dde3e9",
    button_fg="#1f2328",
    button_active_bg="#3b82f6",
    button_active_fg="#ffffff",
    press_bg="#3b82f6",
    press_active_bg="#2563eb",
    success_bg="#22c55e",
    success_active_bg="#16a34a",
    danger_active_bg="#c0485f",
    danger_active_fg="#ffffff",
    log_bg="#ffffff",
    log_fg="#1f2328",
    trough_bg="#c9d1d9",
    row_pady=2,
    text_spacing=(2, 0, 2),
    header_font=("TkDefaultFont", 10, "bold"),
    small_font=("TkDefaultFont", 9, "normal"),
)

CONTRAST = Theme(
    name="contrast",
    window_bg="#000000",
    fg="#ffffff",
    bright_fg="#ffffff",
    muted_fg="#e8e8e8",
    soft_fg="#d0d0d0",
    accent_fg="#00ff9d",
    link_fg="#66c2ff",
    input_bg="#000000",
    input_fg="#ffffff",
    cursor_bg="#ffffff",
    selection_bg="#005fcc",
    button_bg="#1a1a1a",
    button_fg="#ffffff",
    button_active_bg="#005fcc",
    button_active_fg="#ffffff",
    press_bg="#005fcc",
    press_active_bg="#004494",
    success_bg="#00c853",
    success_active_bg="#009940",
    danger_active_bg="#ff1744",
    danger_active_fg="#ffffff",
    log_bg="#000000",
    log_fg="#ffffff",
    trough_bg="#333333",
    row_pady=2,
    text_spacing=(3, 0, 3),
    header_font=("TkDefaultFont", 10, "bold"),
    small_font=("TkDefaultFont", 9, "normal"),
)

THEMES: dict[str, Theme] = {theme.name: theme for theme in (DARK, LIGHT, CONTRAST)}

DEFAULT_THEME_NAME = "dark"

#: Widget roles understood by :func:`style`.
ROLES = (
    "frame",
    "label",
    "muted",
    "soft",
    "small",
    "header",
    "bright",
    "button",
    "danger",
    "text_input",
    "text_log",
    "entry",
    "optionmenu",
    "menu",
    "scrollbar",
)


def theme_names() -> list[str]:
    """Sorted names of the available themes."""
    return sorted(THEMES)


def get_theme(name: object) -> Theme:
    """Resolve a theme name, falling back to ``dark`` on anything unknown."""
    if isinstance(name, str) and name.strip().lower() in THEMES:
        return THEMES[name.strip().lower()]
    return THEMES[DEFAULT_THEME_NAME]


def options(theme: Theme, role: str) -> dict:
    """Tk configure options for ``role`` under ``theme``.

    Raises ``KeyError`` on an unknown role so missing coverage fails
    loudly in tests instead of rendering half-styled widgets.
    """
    spacing1, spacing2, spacing3 = theme.text_spacing
    if role == "frame":
        return {"background": theme.window_bg}
    if role == "label":
        return {"background": theme.window_bg, "foreground": theme.fg}
    if role == "muted":
        return {"background": theme.window_bg, "foreground": theme.muted_fg}
    if role == "soft":
        return {"background": theme.window_bg, "foreground": theme.soft_fg}
    if role == "small":
        return {
            "background": theme.window_bg,
            "foreground": theme.muted_fg,
            "font": theme.small_font,
        }
    if role == "header":
        return {
            "background": theme.window_bg,
            "foreground": theme.bright_fg,
            "font": theme.header_font,
        }
    if role == "bright":
        return {"background": theme.window_bg, "foreground": theme.bright_fg}
    if role == "button":
        return {
            "background": theme.button_bg,
            "foreground": theme.button_fg,
            "activebackground": theme.button_active_bg,
            "activeforeground": theme.button_active_fg,
            "relief": "flat",
            "cursor": "hand2",
        }
    if role == "danger":
        return {
            "background": theme.button_bg,
            "foreground": theme.button_fg,
            "activebackground": theme.danger_active_bg,
            "activeforeground": theme.danger_active_fg,
            "relief": "flat",
            "cursor": "hand2",
        }
    if role == "text_input":
        return {
            "background": theme.input_bg,
            "foreground": theme.input_fg,
            "insertbackground": theme.cursor_bg,
            "selectbackground": theme.selection_bg,
            "selectforeground": theme.input_fg,
            "spacing1": spacing1,
            "spacing2": spacing2,
            "spacing3": spacing3,
            "relief": "flat",
            "highlightthickness": 1,
            "highlightbackground": theme.trough_bg,
        }
    if role == "text_log":
        return {
            "background": theme.log_bg,
            "foreground": theme.log_fg,
            "insertbackground": theme.cursor_bg,
            "selectbackground": theme.selection_bg,
            "selectforeground": theme.log_fg,
            "spacing1": spacing1,
            "spacing2": spacing2,
            "spacing3": spacing3,
            "relief": "flat",
        }
    if role == "entry":
        return {
            "background": theme.input_bg,
            "foreground": theme.input_fg,
            "insertbackground": theme.cursor_bg,
            "selectbackground": theme.selection_bg,
            "selectforeground": theme.input_fg,
            "relief": "flat",
        }
    if role == "optionmenu":
        return {
            "background": theme.button_bg,
            "foreground": theme.button_fg,
            "activebackground": theme.button_active_bg,
            "activeforeground": theme.button_active_fg,
            "relief": "flat",
        }
    if role == "menu":
        return {
            "background": theme.input_bg,
            "foreground": theme.input_fg,
            "activebackground": theme.selection_bg,
            "activeforeground": theme.input_fg,
        }
    if role == "scrollbar":
        return {
            "background": theme.button_bg,
            "troughcolor": theme.trough_bg,
            "activebackground": theme.button_active_bg,
            "relief": "flat",
        }
    raise KeyError(f"unknown widget role `{role}`")
