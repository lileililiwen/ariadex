## Design

Add one geometry-clamping helper that receives the virtual-screen origin and
dimensions, widget width/height, and configured margin. It returns coordinates
that keep the complete active dialog inside the usable screen rectangle. Use
Tk's virtual-screen bounds so negative multi-monitor origins are supported.

Use the helper at initial placement, after loading saved coordinates, during
title-bar drag motion, and after expanded/collapsed geometry changes. Persist
only the clamped coordinates. If a screen is smaller than the requested
widget, clamp to the screen origin and preserve the title bar/close control;
the widget must never become unreachable.

Dragging remains available only from the title bar, preserving button and
text interaction. Geometry failures remain fail-soft and must not stop daemon
polling or provider supervision.
