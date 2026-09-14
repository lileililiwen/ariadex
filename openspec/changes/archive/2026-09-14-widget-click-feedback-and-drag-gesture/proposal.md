# Proposal: widget click feedback and drag gesture

## Why

The floating widget already exposes the required controls, but clicks have no
explicit acknowledgement and the draggable title area does not communicate
that it can be dragged. This makes slow IPC look like a missed click and makes
window movement undiscoverable.

## What Changes

Add immediate pressed/success feedback to widget buttons and mark only the
title area as a hand-cursor drag surface. Button surfaces remain independent
click targets.

Non-goals: changing daemon/provider lifecycle, changing button commands, or
adding platform-specific window-management APIs.
