# Tasks

- [x] Add the `Close` button to the hub controls row wired to
      `_on_close_window`; verify under real Tk on Xvfb.
- [x] Size the hub window with `HUB_COLLAPSED_HEIGHT`/`HUB_EXPANDED_HEIGHT`
      so the controls row is reachable collapsed and expanded (measured on
      Tk; single-widget sizes untouched).
- [x] Add regression tests (button exists, invoke closes only the window:
      no watcher callbacks, root destroyed; geometry uses hub heights);
      update README and `docs/PROJECT-GUIDE.md`; verify with the full
      suite, Ruff, mypy, coverage floors, and strict OpenSpec validation.

