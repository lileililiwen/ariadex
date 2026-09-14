The companion keeps independent `_refresh_busy` and `_action_busy` flags. A
status poll suppresses only another poll; it never suppresses a user action.
All managed actions use the existing bounded client in a worker thread and
marshal state rendering back to Tk. Quit destroys the widget only after the
daemon confirms the stop request.
