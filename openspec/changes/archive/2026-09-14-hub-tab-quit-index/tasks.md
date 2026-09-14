# Tasks

- [x] Route `_on_quit_active` through `remove_project`; clamp the active
      index at the top of `_render`.
- [x] Add a regression test (quit middle tab, click remaining buttons,
      expand works); verify under real Tk on Xvfb plus the full suite,
      Ruff, mypy, coverage floors, and strict OpenSpec validation.
