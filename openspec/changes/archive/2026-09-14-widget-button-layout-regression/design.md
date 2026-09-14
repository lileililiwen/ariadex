# Design

The 340px inner width of the 360px widget is shared by four packed buttons.
Primary buttons use a six-character requested width with reduced padding;
Copy log uses an eight-character width. `expand=True, fill="x"` continues to
give each action an equal usable cell while the requested sizes remain below
the available width. The collapsed window height and action order are
unchanged.

